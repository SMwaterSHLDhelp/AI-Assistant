"""Small web lookup for the running game. No browser, no API key required."""

from __future__ import annotations

import gzip
import hashlib
import http.client
import ipaddress
import json
import os
import time
import urllib.parse
import urllib.robotparser
from collections.abc import Callable
from html.parser import HTMLParser
from typing import Any

from .http_util import USER_AGENT, check_url

SEARCH_PROVIDERS = ("duckduckgo", "searxng", "brave", "tavily", "serper")
PREFERRED_HOSTS = (
    "fandom.com",
    "wiki.gg",
    "pcgamingwiki.com",
    "steamcommunity.com",
    "steampowered.com",
)
CACHE_SECONDS = 24 * 60 * 60
MIN_INTERVAL = 1.5
SEARCH_TIMEOUT = 8
PAGE_TIMEOUT = 8
ROBOTS_TIMEOUT = 4
MAX_PAGE_BYTES = 400_000
MAX_TEXT = 3500
MAX_RESULTS = 6
MAX_REDIRECTS = 3
BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

Fetch = Callable[..., tuple[int, bytes]]
Sleep = Callable[[float], None]


def normalize_web(raw: Any) -> dict[str, Any]:
    prefs = {
        "enabled": True,
        "provider": "duckduckgo",
        "searxng_url": "",
        "brave_key": "",
        "tavily_key": "",
        "serper_key": "",
    }
    if isinstance(raw, dict):
        if "enabled" in raw:
            prefs["enabled"] = bool(raw["enabled"])
        provider = str(raw.get("provider") or "").strip().lower()
        if provider in SEARCH_PROVIDERS:
            prefs["provider"] = provider
        prefs["searxng_url"] = str(raw.get("searxng_url") or "").strip()[:300]
        for key in ("brave_key", "tavily_key", "serper_key"):
            if key in raw and raw[key] is not None:
                prefs[key] = str(raw[key]).strip()[:400]
    return prefs


def public_web(raw: Any) -> dict[str, Any]:
    prefs = normalize_web(raw)
    return {
        "enabled": prefs["enabled"],
        "provider": prefs["provider"],
        "searxng_url": prefs["searxng_url"],
        "has_brave_key": bool(prefs["brave_key"]),
        "has_tavily_key": bool(prefs["tavily_key"]),
        "has_serper_key": bool(prefs["serper_key"]),
    }


def _host(url: str) -> str:
    return (urllib.parse.urlsplit(url).hostname or "").lower().rstrip(".")


def blocked_host(host: str) -> bool:
    name = (host or "").lower().rstrip(".")
    if not name or name == "localhost" or name.endswith(".localhost") or name.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(name)
    except ValueError:
        return False
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


def _connection(parts: urllib.parse.SplitResult, timeout: float) -> http.client.HTTPConnection:
    host = parts.hostname or ""
    if parts.scheme == "https":
        return http.client.HTTPSConnection(host, parts.port or 443, timeout=timeout)
    return http.client.HTTPConnection(host, parts.port or 80, timeout=timeout)


def _path_of(parts: urllib.parse.SplitResult) -> str:
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return path


def fetch_url(
    url: str,
    timeout: float,
    max_bytes: int,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    method: str = "GET",
) -> tuple[int, bytes]:
    """Fetch one public URL, following a few redirects. Status codes are returned, not raised."""
    current = url
    payload = body
    verb = method.upper()
    for _hop in range(MAX_REDIRECTS + 1):
        parts = check_url(current)
        if blocked_host(parts.hostname or ""):
            raise ValueError("That address is not a public web page")
        outgoing = {"User-Agent": USER_AGENT, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"}
        if headers and verb == method.upper() and current == url:
            outgoing.update(headers)
        if payload is not None:
            outgoing["Content-Length"] = str(len(payload))
        conn = _connection(parts, timeout)
        try:
            conn.request(verb, _path_of(parts), body=payload, headers=outgoing)
            response = conn.getresponse()
            status = response.status
            if status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location") or ""
                response.read(1024)
                if not location:
                    raise ValueError("The site redirected without a destination")
                current = urllib.parse.urljoin(current, location)
                payload = None
                verb = "GET"
                continue
            raw = b""
            while len(raw) < max_bytes:
                chunk = response.read(min(8192, max_bytes - len(raw)))
                if not chunk:
                    break
                raw += chunk
            encoding = (response.getheader("Content-Encoding") or "").lower()
            if "gzip" in encoding or raw[:2] == b"\x1f\x8b":
                try:
                    raw = gzip.decompress(raw)
                except (OSError, EOFError, gzip.BadGzipFile):
                    pass
            return status, raw
        finally:
            conn.close()
    raise ValueError("The site redirected too many times")


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.in_title = False
        self.title: list[str] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg", "iframe", "canvas"}:
            self.skip += 1
        if tag == "title":
            self.in_title = True
        if tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg", "iframe", "canvas"} and self.skip:
            self.skip -= 1
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        if self.in_title:
            self.title.append(data)
        elif data:
            self.parts.append(data)


def extract_text(page: str, limit: int = MAX_TEXT) -> tuple[str, str]:
    parser = _Extractor()
    try:
        parser.feed(page)
        parser.close()
    except Exception:
        return "", ""
    title = " ".join("".join(parser.title).split())[:160]
    chunks = []
    for line in "".join(parser.parts).splitlines():
        cleaned = " ".join(line.split())
        if len(cleaned) > 1:
            chunks.append(cleaned)
    return title, "\n".join(chunks)[:limit]


class _DuckParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._href = ""
        self._title: list[str] = []
        self._snippet: list[str] = []
        self._mode = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        classes = values.get("class", "")
        if tag == "a" and ("result__a" in classes or "result-link" in classes):
            self._flush()
            self._href = values.get("href", "")
            self._mode = "title"
        elif "result__snippet" in classes or "result-snippet" in classes:
            self._mode = "snippet"

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._mode == "title":
            self._mode = ""
        if tag in {"td", "a"} and self._mode == "snippet":
            self._mode = ""

    def handle_data(self, data: str) -> None:
        if self._mode == "title":
            self._title.append(data)
        elif self._mode == "snippet":
            self._snippet.append(data)

    def _flush(self) -> None:
        if self._href:
            self.results.append(
                {
                    "title": " ".join("".join(self._title).split()),
                    "url": _duck_target(self._href),
                    "snippet": " ".join("".join(self._snippet).split()),
                }
            )
        self._href = ""
        self._title = []
        self._snippet = []

    def close(self) -> None:
        self._flush()
        super().close()


def _duck_target(href: str) -> str:
    parsed = urllib.parse.urlsplit(href)
    query = urllib.parse.parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return query["uddg"][0]
    if href.startswith("//"):
        return "https:" + href
    return href


def parse_duckduckgo(page: str) -> list[dict[str, str]]:
    parser = _DuckParser()
    try:
        parser.feed(page)
        parser.close()
    except Exception:
        return []
    return [item for item in parser.results if item["url"].startswith("http")]


def _rank(url: str) -> int:
    host = _host(url)
    for index, domain in enumerate(PREFERRED_HOSTS):
        if host == domain or host.endswith("." + domain):
            return index
    return len(PREFERRED_HOSTS)


def prefer_game_sources(results: list[dict[str, str]]) -> list[dict[str, str]]:
    decorated = list(enumerate(results))
    decorated.sort(key=lambda item: (_rank(item[1].get("url") or ""), item[0]))
    return [item for _index, item in decorated]


def _clip(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


class WebClient:
    """Search and page fetch with a disk cache, robots.txt, and a per-host pause."""

    def __init__(
        self,
        cache_dir: str,
        settings: dict[str, Any] | None = None,
        fetch: Fetch | None = None,
        sleep: Sleep | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.settings = normalize_web(settings)
        self.fetch = fetch or fetch_url
        self.sleep = sleep or time.sleep
        self.clock = clock or time.monotonic
        self.sources: list[dict[str, str]] = []
        self._seen: dict[str, float] = {}
        self.enabled = bool(self.settings["enabled"])
        self.last_error = ""

    def search(self, query: str, now: float | None = None) -> list[dict[str, str]]:
        text = " ".join(str(query or "").split())[:300]
        if not text or not self.enabled:
            return []
        stamp = time.time() if now is None else now
        self.last_error = ""
        cached = self._read_cache("search", self._search_key(text), stamp)
        if isinstance(cached, list):
            results = [item for item in cached if isinstance(item, dict)]
            self._remember(results)
            return results
        try:
            results = self._search_live(text)
        except Exception as exc:
            self.last_error = " ".join(str(exc).split())[:300]
            return []
        results = prefer_game_sources(results)[:MAX_RESULTS]
        cleaned = [
            {"title": _clip(item.get("title"), 140), "url": item.get("url") or "", "snippet": _clip(item.get("snippet"), 280)}
            for item in results
            if str(item.get("url") or "").startswith("http")
        ]
        if cleaned:
            self._write_cache("search", self._search_key(text), cleaned, stamp)
            self._remember(cleaned)
        return cleaned

    def fetch_page(self, url: str, now: float | None = None) -> dict[str, str]:
        target = str(url or "").strip()
        if not self.enabled:
            return {"url": target, "title": "", "text": ""}
        stamp = time.time() if now is None else now
        cached = self._read_cache("page", target, stamp)
        if isinstance(cached, dict) and cached.get("text"):
            self._remember([cached])
            return {"url": target, "title": str(cached.get("title") or ""), "text": str(cached.get("text") or "")}
        try:
            final, _status, body = self._get_public(target, PAGE_TIMEOUT, MAX_PAGE_BYTES)
        except Exception as exc:
            return {"url": target, "title": "", "text": str(exc)[:200]}
        if not self._robots_allow(final):
            return {"url": final, "title": "", "text": "Skipped. This site's robots.txt disallows automated reading."}
        title, text = extract_text(body.decode("utf-8", "replace"))
        page = {"url": final, "title": title, "text": text}
        if text:
            self._write_cache("page", target, page, stamp)
            self._remember([page])
        return page

    def auto(self, game: str, question: str, now: float | None = None) -> str:
        """Snippets for a model that cannot call tools. Empty when lookup is off or nothing useful came back."""
        if not self.enabled:
            return ""
        name = _clip(game, 120)
        ask = _clip(question, 180)
        if not ask and not name:
            return ""
        query = f"{name} {ask}".strip()
        results = self.search(query, now=now)
        if not results:
            return ""
        lines = ["Web lookup (short excerpts):"]
        for item in results[:4]:
            lines.append(f"- {item['title']} — {item['url']}")
            if item.get("snippet"):
                lines.append(f"  {item['snippet']}")
        return "\n".join(lines)[:1500]

    def _search_key(self, query: str) -> str:
        provider = self.settings["provider"]
        extra = self.settings["searxng_url"] if provider == "searxng" else ""
        return f"{provider}\n{extra}\n{query.lower()}"

    def _search_live(self, query: str) -> list[dict[str, str]]:
        provider = self.settings["provider"]
        if provider == "searxng":
            return self._searxng(query)
        if provider == "brave":
            return self._brave(query)
        if provider == "tavily":
            return self._tavily(query)
        if provider == "serper":
            return self._serper(query)
        return self._duckduckgo(query)

    def _duckduckgo(self, query: str) -> list[dict[str, str]]:
        form = urllib.parse.urlencode({"q": query, "kl": "us-en"}).encode("utf-8")
        headers = {
            "User-Agent": BROWSER_UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://html.duckduckgo.com/",
        }
        errors: list[str] = []
        query_string = urllib.parse.urlencode({"q": query})
        attempts: tuple[tuple[str, str, bytes | None], ...] = (
            ("POST", "https://html.duckduckgo.com/html/", form),
            ("GET", "https://html.duckduckgo.com/html/?" + query_string, None),
            ("POST", "https://lite.duckduckgo.com/lite/", form),
            ("GET", "https://lite.duckduckgo.com/lite/?" + query_string, None),
        )
        for method, url, payload in attempts:
            try:
                _url, status, body = self._get_public(
                    url,
                    SEARCH_TIMEOUT,
                    MAX_PAGE_BYTES,
                    headers=headers,
                    body=payload,
                    method=method,
                )
            except Exception as exc:
                errors.append(" ".join(str(exc).split())[:180])
                continue
            if status == 202 or status >= 400:
                errors.append(f"DuckDuckGo returned HTTP {status}")
                continue
            page = body.decode("utf-8", "replace")
            results = parse_duckduckgo(page)
            if results:
                return results
            lowered = page.lower()
            if "anomaly" in lowered or "captcha" in lowered or "unfortunately, bots" in lowered:
                errors.append("DuckDuckGo asked for a browser check")
            else:
                errors.append("DuckDuckGo returned no results")
        if errors:
            raise ValueError(errors[-1])
        return []

    def _searxng(self, query: str) -> list[dict[str, str]]:
        base = self.settings["searxng_url"].rstrip("/")
        if not base:
            raise ValueError("Add a SearXNG URL in settings")
        url = base + "/search?" + urllib.parse.urlencode({"q": query, "format": "json", "categories": "general"})
        _url, _status, body = self._get_public(url, SEARCH_TIMEOUT, MAX_PAGE_BYTES)
        payload = json.loads(body.decode("utf-8", "replace") or "{}")
        found = []
        for item in payload.get("results") or []:
            if isinstance(item, dict) and item.get("url"):
                found.append({"title": item.get("title") or "", "url": item["url"], "snippet": item.get("content") or ""})
        return found

    def _brave(self, query: str) -> list[dict[str, str]]:
        key = self.settings["brave_key"]
        if not key:
            raise ValueError("Add a Brave API key in settings")
        url = "https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode({"q": query, "count": MAX_RESULTS})
        _url, _status, body = self._get_public(url, SEARCH_TIMEOUT, MAX_PAGE_BYTES, headers={"X-Subscription-Token": key})
        payload = json.loads(body.decode("utf-8", "replace") or "{}")
        rows = ((payload.get("web") or {}).get("results") or []) if isinstance(payload, dict) else []
        return [
            {"title": item.get("title") or "", "url": item.get("url") or "", "snippet": item.get("description") or ""}
            for item in rows
            if isinstance(item, dict)
        ]

    def _tavily(self, query: str) -> list[dict[str, str]]:
        key = self.settings["tavily_key"]
        if not key:
            raise ValueError("Add a Tavily API key in settings")
        payload = json.dumps({"api_key": key, "query": query, "max_results": MAX_RESULTS}).encode("utf-8")
        _url, _status, body = self._get_public(
            "https://api.tavily.com/search",
            SEARCH_TIMEOUT,
            MAX_PAGE_BYTES,
            headers={"Content-Type": "application/json"},
            body=payload,
            method="POST",
        )
        data = json.loads(body.decode("utf-8", "replace") or "{}")
        return [
            {"title": item.get("title") or "", "url": item.get("url") or "", "snippet": item.get("content") or ""}
            for item in (data.get("results") or [])
            if isinstance(item, dict)
        ]

    def _serper(self, query: str) -> list[dict[str, str]]:
        key = self.settings["serper_key"]
        if not key:
            raise ValueError("Add a Serper API key in settings")
        payload = json.dumps({"q": query, "num": MAX_RESULTS}).encode("utf-8")
        _url, _status, body = self._get_public(
            "https://google.serper.dev/search",
            SEARCH_TIMEOUT,
            MAX_PAGE_BYTES,
            headers={"X-API-KEY": key, "Content-Type": "application/json"},
            body=payload,
            method="POST",
        )
        data = json.loads(body.decode("utf-8", "replace") or "{}")
        return [
            {"title": item.get("title") or "", "url": item.get("link") or "", "snippet": item.get("snippet") or ""}
            for item in (data.get("organic") or [])
            if isinstance(item, dict)
        ]

    def _get_public(
        self,
        url: str,
        timeout: float,
        max_bytes: int,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        method: str = "GET",
    ) -> tuple[str, bytes]:
        host = _host(url)
        if blocked_host(host):
            raise ValueError("That address is not a public web page")
        self._pace(host)
        status, raw = self.fetch(url, timeout, max_bytes, headers=headers, body=body, method=method)
        if status >= 400:
            raise ValueError(f"The site returned HTTP {status}")
        return url, status, raw

    def _pace(self, host: str) -> None:
        now = self.clock()
        last = self._seen.get(host)
        if last is not None:
            wait = MIN_INTERVAL - (now - last)
            if wait > 0:
                self.sleep(min(wait, 2))
        self._seen[host] = self.clock()

    def _robots_allow(self, url: str) -> bool:
        host = _host(url)
        cached = self._read_cache("robots", host, time.time())
        lines: list[str]
        if isinstance(cached, dict) and isinstance(cached.get("body"), str):
            lines = cached["body"].splitlines()
        else:
            scheme = "https" if url.startswith("https") else "http"
            robots_url = urllib.parse.urlunsplit((scheme, host, "/robots.txt", "", ""))
            try:
                if blocked_host(host):
                    return False
                self._pace(host)
                status, raw = self.fetch(robots_url, ROBOTS_TIMEOUT, 64_000)
            except Exception:
                return False
            if status == 404:
                text = "User-agent: *\nAllow: /\n"
            elif status >= 400:
                return False
            else:
                text = raw.decode("utf-8", "replace") or "User-agent: *\nAllow: /\n"
            self._write_cache("robots", host, {"body": text[:64_000]}, time.time())
            lines = text.splitlines()
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(lines)
        return parser.can_fetch(USER_AGENT, url)

    def _remember(self, rows: list[dict[str, Any]]) -> None:
        seen = {item["url"] for item in self.sources}
        for item in rows:
            url = str(item.get("url") or "")
            if not url.startswith("http") or url in seen:
                continue
            self.sources.append({"title": _clip(item.get("title") or url, 140), "url": url})
            seen.add(url)
            if len(self.sources) >= MAX_RESULTS:
                break

    def _path(self, kind: str, key: str) -> str:
        digest = hashlib.sha256(f"{kind}\n{key}".encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{kind}-{digest}.json")

    def _read_cache(self, kind: str, key: str, now: float) -> Any:
        path = self._path(kind, key)
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or now - float(data.get("fetched_at") or 0) > CACHE_SECONDS:
            return None
        return data.get("value")

    def _write_cache(self, kind: str, key: str, value: Any, now: float) -> None:
        os.makedirs(self.cache_dir, exist_ok=True)
        os.chmod(self.cache_dir, 0o700)
        path = self._path(kind, key)
        temporary = path + ".partial"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump({"fetched_at": now, "value": value}, handle)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
