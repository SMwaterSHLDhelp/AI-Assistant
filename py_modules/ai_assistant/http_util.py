"""Stdlib HTTP helper. Request headers and bodies are never logged."""

from __future__ import annotations

import http.client
import json
import threading
import urllib.parse
from collections.abc import Iterator
from typing import Any

from .redact import redact

USER_AGENT = "Deckling-Decky/0.1.0"
_MAX_BODY = 8 * 1024 * 1024
_MAX_ERROR = 8 * 1024


class HttpError(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(message)


def check_url(url: str) -> urllib.parse.SplitResult:
    parts = urllib.parse.urlsplit((url or "").strip())
    if parts.scheme not in {"http", "https"}:
        raise ValueError("Provider URL must start with http:// or https://")
    if not parts.hostname:
        raise ValueError("Provider URL is missing a host")
    if parts.username or parts.password:
        raise ValueError("Provider URL must not include a username or password")
    return parts


def join_url(base: str, suffix: str) -> str:
    return base.rstrip("/") + "/" + suffix.lstrip("/")


def _path_of(parts: urllib.parse.SplitResult) -> str:
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return path


def _connection(parts: urllib.parse.SplitResult, timeout: float) -> http.client.HTTPConnection:
    host = parts.hostname or ""
    if parts.scheme == "https":
        return http.client.HTTPSConnection(host, parts.port or 443, timeout=timeout)
    return http.client.HTTPConnection(host, parts.port or 80, timeout=timeout)


def request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = 30,
) -> tuple[int, bytes]:
    """Perform one request and return ``(status, body)``. Raises ``HttpError`` on HTTP errors."""
    parts = check_url(url)
    conn = _connection(parts, timeout)
    outgoing = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        outgoing.update(headers)
    try:
        conn.request(method.upper(), _path_of(parts), body=body, headers=outgoing)
        response = conn.getresponse()
        status = response.status
        if status >= 400:
            raw = response.read(_MAX_ERROR)
            message = redact(raw.decode("utf-8", "replace")).strip() or response.reason
            raise HttpError(status, f"HTTP {status}: {message[:400]}")
        raw = response.read(_MAX_BODY + 1)
        if len(raw) > _MAX_BODY:
            raise HttpError(status, "Response was larger than the plugin allows")
        return status, raw
    finally:
        conn.close()


def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    form: dict[str, str] | None = None,
    timeout: float = 30,
) -> Any:
    body: bytes | None = None
    outgoing = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        outgoing.setdefault("Content-Type", "application/json")
    elif form is not None:
        body = urllib.parse.urlencode(form).encode("utf-8")
        outgoing.setdefault("Content-Type", "application/x-www-form-urlencoded")
    status, raw = request(method, url, headers=outgoing, body=body, timeout=timeout)
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HttpError(status, "Provider returned a response that was not JSON") from exc


def iter_lines(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = 120,
    cancel: threading.Event | None = None,
) -> Iterator[str]:
    """Yield decoded lines from a streaming response. ``cancel`` closes the socket."""
    parts = check_url(url)
    conn = _connection(parts, timeout)
    outgoing = {"User-Agent": USER_AGENT, "Accept": "text/event-stream"}
    if headers:
        outgoing.update(headers)
    finished = threading.Event()
    user_cancel = cancel or threading.Event()

    def _close() -> None:
        try:
            conn.close()
        except Exception:
            pass

    def _watch() -> None:
        while not finished.is_set():
            if user_cancel.is_set():
                _close()
                return
            finished.wait(0.2)

    threading.Thread(target=_watch, daemon=True).start()
    try:
        conn.request(method.upper(), _path_of(parts), body=body, headers=outgoing)
        response = conn.getresponse()
        if response.status >= 400:
            raw = response.read(_MAX_ERROR)
            message = redact(raw.decode("utf-8", "replace")).strip() or response.reason
            raise HttpError(response.status, f"HTTP {response.status}: {message[:400]}")
        while not user_cancel.is_set():
            try:
                line = response.readline()
            except Exception:
                if user_cancel.is_set():
                    return
                raise
            if not line:
                return
            yield line.decode("utf-8", "replace").rstrip("\r\n")
    finally:
        finished.set()
        _close()
