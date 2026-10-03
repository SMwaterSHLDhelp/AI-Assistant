"""Web lookup with mocked HTTP. No live search engines."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ai_assistant.service import AssistantService
from ai_assistant.web import WebClient, extract_text, prefer_game_sources

DDG = b"""
<html><body>
<a class="result__a" href="https://example.com/random">Random</a>
<a class="result__snippet">Not about the game.</a>
<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.pcgamingwiki.com%2Fwiki%2FElden_Ring">Elden Ring</a>
<a class="result__snippet">A big tree.</a>
</body></html>
"""

PAGE = b"<html><title>Grace</title><script>secret()</script><p>The grace is north.</p></html>"
ROBOTS_BLOCK = b"User-agent: *\nDisallow: /\n"


def _fetch_factory(pages: dict[str, tuple[int, bytes]]):
    def fetch(url, timeout, max_bytes, headers=None, body=None, method="GET"):  # noqa: ARG001
        for prefix, payload in pages.items():
            if url.startswith(prefix):
                return payload
        return 404, b""

    return fetch


def test_search_prefers_game_wikis_and_caches(tmp_path) -> None:
    calls: list[str] = []

    def fetch(url, timeout, max_bytes, headers=None, body=None, method="GET"):  # noqa: ARG001
        calls.append(url)
        if url.endswith("/robots.txt"):
            return 404, b""
        return 200, DDG

    client = WebClient(str(tmp_path), {"provider": "duckduckgo"}, fetch=fetch, sleep=lambda _seconds: None)
    first = client.search("Elden Ring grace", now=10)
    second = client.search("Elden Ring grace", now=11)
    assert first[0]["url"].startswith("https://www.pcgamingwiki.com/")
    assert first[0]["snippet"] == "A big tree."
    assert second == first
    assert len(calls) == 1
    mode = (tmp_path / next(tmp_path.iterdir()).name).stat().st_mode & 0o777
    assert mode == 0o600


def test_page_extract_skips_script_and_obeys_robots(tmp_path) -> None:
    title, text = extract_text(PAGE.decode())
    assert title == "Grace"
    assert "north" in text
    assert "secret" not in text

    def fetch(url, timeout, max_bytes, headers=None, body=None, method="GET"):  # noqa: ARG001
        if url.endswith("/robots.txt"):
            return 200, ROBOTS_BLOCK
        return 200, PAGE

    client = WebClient(str(tmp_path), fetch=fetch, sleep=lambda _seconds: None)
    blocked = client.fetch_page("https://wiki.example/page", now=5)
    assert "robots.txt" in blocked["text"]
    assert "north" not in blocked["text"]


def test_private_addresses_are_not_fetched(tmp_path) -> None:
    calls: list[str] = []

    def fetch(url, timeout, max_bytes, headers=None, body=None, method="GET"):  # noqa: ARG001
        calls.append(url)
        return 200, PAGE

    client = WebClient(str(tmp_path), fetch=fetch, sleep=lambda _seconds: None)
    result = client.fetch_page("http://127.0.0.1/secret", now=5)
    assert calls == []
    assert "public" in result["text"]


def test_rate_limit_pauses_between_hits_on_one_host(tmp_path) -> None:
    slept: list[float] = []
    clock = {"now": 0.0}

    def fetch(url, timeout, max_bytes, headers=None, body=None, method="GET"):  # noqa: ARG001
        if url.endswith("/robots.txt"):
            return 404, b""
        return 200, PAGE

    client = WebClient(
        str(tmp_path),
        fetch=fetch,
        sleep=slept.append,
        clock=lambda: clock["now"],
    )
    client.fetch_page("https://wiki.example/one", now=1)
    client.fetch_page("https://wiki.example/two", now=2)
    assert slept and slept[0] > 0


def test_ranking_puts_steam_and_wikis_first() -> None:
    ranked = prefer_game_sources(
        [
            {"title": "Random", "url": "https://example.com/a", "snippet": ""},
            {"title": "Store", "url": "https://store.steampowered.com/app/1", "snippet": ""},
            {"title": "Wiki", "url": "https://game.wiki.gg/wiki/A", "snippet": ""},
        ]
    )
    assert "wiki.gg" in ranked[0]["url"]
    assert "steampowered" in ranked[1]["url"]


def test_disabled_lookup_and_saved_keys_stay_out_of_state(tmp_path) -> None:
    service = AssistantService(str(tmp_path / "settings"), str(tmp_path / "runtime"))
    saved = service.save_web({"provider": "brave", "brave_key": "brave-secret-value"})
    assert saved["web"]["has_brave_key"] is True
    assert "brave-secret-value" not in json.dumps(saved)
    state = service.state()
    assert "brave-secret-value" not in json.dumps(state)
    assert state["web"]["provider"] == "brave"
    service.save_web({"enabled": False})
    client = WebClient(str(tmp_path / "cache"), service.store.load_config()["web"], fetch=lambda *args, **kwargs: (200, DDG))
    assert client.search("Elden Ring") == []
    assert client.auto("Elden Ring", "where is the grace") == ""


def test_tool_call_uses_mocked_search_and_records_the_source(tmp_path, monkeypatch) -> None:
    def fetch(url, timeout, max_bytes, headers=None, body=None, method="GET"):  # noqa: ARG001
        if "duckduckgo" in url:
            return 200, DDG
        if url.endswith("/robots.txt"):
            return 404, b""
        return 200, PAGE

    monkeypatch.setattr("ai_assistant.web.fetch_url", fetch)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length))
            used_tool = any(item.get("role") == "tool" for item in payload.get("messages") or [])
            if used_tool:
                raw = (
                    b'data: {"choices":[{"delta":{"content":"The grace is north."}}]}\n\n'
                    b"data: [DONE]\n\n"
                )
            else:
                call = json.dumps(
                    {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": "c1",
                                            "function": {
                                                "name": "web_search",
                                                "arguments": json.dumps({"query": "Elden Ring grace"}),
                                            },
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ).encode()
                raw = b"data: " + call + b"\n\ndata: [DONE]\n\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, fmt: str, *args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host_events: list[dict] = []

    class Host:
        async def emit(self, event: str, payload: dict) -> None:
            host_events.append(payload)

        def info(self, message: str, *args: object) -> None:
            return None

        def warning(self, message: str, *args: object) -> None:
            return None

    service = AssistantService(str(tmp_path / "settings"), str(tmp_path / "runtime"), Host())
    try:
        saved = service.save_provider(
            {
                "kind": "custom",
                "name": "Local",
                "base_url": f"http://127.0.0.1:{server.server_address[1]}/v1",
                "default_model": "test-model",
                "api_key": "sk-test",
            }
        )

        async def run() -> None:
            import asyncio

            service.start_chat(saved["provider"]["id"], "test-model", "Where is the grace?", "req-web", "")
            for _ in range(50):
                if any(item.get("type") == "chat_done" for item in host_events):
                    break
                await asyncio.sleep(0.05)
            await service.shutdown()

        import asyncio

        asyncio.run(run())
    finally:
        server.shutdown()

    done = next(item for item in host_events if item.get("type") == "chat_done")
    assert done["text"] == "The grace is north."
    sources = done["messages"][-1]["sources"]
    assert sources[0]["url"].startswith("https://www.pcgamingwiki.com/")
    assert any(item.get("type") == "web" and item.get("phase") == "searching" for item in host_events)
    assert "sk-test" not in json.dumps(host_events)
