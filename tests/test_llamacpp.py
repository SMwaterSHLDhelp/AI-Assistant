import asyncio
import json
import os
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ai_assistant.http_util import HttpError
from ai_assistant.providers import _explain_llamacpp, _ids_from_openai_payload, iter_text, list_models
from ai_assistant.service import AssistantService


class _Host:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def emit(self, event: str, payload: dict) -> None:
        self.events.append(payload)

    def info(self, message: str, *args: object) -> None:
        return None

    def warning(self, message: str, *args: object) -> None:
        return None


def _serve(handler: type[BaseHTTPRequestHandler]) -> tuple[ThreadingHTTPServer, int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


def _sse(text: str) -> bytes:
    payload = json.dumps({"choices": [{"delta": {"content": text}}]})
    return f"data: {payload}\n\ndata: [DONE]\n\n".encode()


def test_openai_delta_keeps_reasoning_when_content_is_null() -> None:
    from ai_assistant.providers import _openai_delta

    assert _openai_delta({"choices": [{"delta": {"content": None}}]}) == ""
    assert _openai_delta({"choices": [{"delta": {"reasoning_content": "pong"}}]}) == "pong"
    assert _openai_delta({"choices": [{"delta": {"content": "pong", "reasoning_content": "think"}}]}) == "pong"


def test_llamacpp_adds_v1_and_uses_the_only_loaded_model() -> None:
    seen: list[tuple[str, bytes]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            seen.append((self.path, b""))
            body = json.dumps({"data": [{"id": "qwen-test"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            seen.append((self.path, self.rfile.read(length)))
            body = _sse("pong")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            return None

    server, port = _serve(Handler)
    try:
        provider = {"kind": "llamacpp", "base_url": f"http://127.0.0.1:{port}", "default_model": ""}
        assert list_models(provider) == ["qwen-test"]
        text = "".join(
            iter_text(provider, [{"role": "user", "content": "ping"}], "", threading.Event())
        )
    finally:
        server.shutdown()

    assert text == "pong"
    assert seen[0][0] == "/v1/models"
    post = next(item for item in seen if item[0] == "/v1/chat/completions")
    posted = json.loads(post[1])
    assert posted["model"] == "qwen-test"


def test_llamacpp_keeps_an_existing_v1_suffix_and_sends_the_api_key() -> None:
    captured: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            captured.setdefault("paths", []).append(self.path)
            captured["auth"] = self.headers.get("Authorization") or ""
            body = json.dumps({"data": [{"id": "tiny"}, {"id": "other"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            return None

    server, port = _serve(Handler)
    try:
        provider = {
            "kind": "llamacpp",
            "base_url": f"http://127.0.0.1:{port}/v1/",
            "api_key": "deck-secret",
        }
        models = list_models(provider)
        with pytest.raises(ValueError, match="more than one model"):
            list(iter_text(provider, [{"role": "user", "content": "hi"}], "", threading.Event()))
    finally:
        server.shutdown()

    assert models == ["other", "tiny"]
    assert captured["paths"][0] == "/v1/models"
    assert "/props" in captured["paths"]
    assert captured["auth"] == "Bearer deck-secret"


def test_llamacpp_reports_loading_auth_and_down_server(tmp_path) -> None:
    class Loading(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = b'{"error":{"message":"Loading model","code":503}}'
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            return None

    class Locked(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = b"Unauthorized"
            self.send_response(401)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            return None

    loading, loading_port = _serve(Loading)
    locked, locked_port = _serve(Locked)
    host = _Host()
    service = AssistantService(str(tmp_path / "settings"), str(tmp_path / "runtime"), host)
    try:
        with pytest.raises(HttpError, match="still loading"):
            list_models({"kind": "llamacpp", "base_url": f"http://127.0.0.1:{loading_port}"})
        with pytest.raises(HttpError, match="rejected the API key"):
            list_models({"kind": "llamacpp", "base_url": f"http://127.0.0.1:{locked_port}/v1"})
        saved = service.save_provider(
            {"kind": "llamacpp", "name": "Down", "base_url": "http://127.0.0.1:9/v1"}
        )

        async def run() -> dict:
            return await service.test_provider(saved["provider"]["id"])

        result = asyncio.run(run())
    finally:
        loading.shutdown()
        locked.shutdown()

    assert result["ok"] is False
    assert "Can't reach llama-server" in result["error"]
    assert "Errno" not in result["error"]


def test_llamacpp_chat_sends_earlier_turns(tmp_path) -> None:
    bodies: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = json.dumps({"data": [{"id": "qwen-test"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            bodies.append(json.loads(self.rfile.read(length)))
            reply = "blue" if len(bodies) == 1 else "you said blue"
            raw = _sse(reply)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, fmt: str, *args: object) -> None:
            return None

    server, port = _serve(Handler)
    host = _Host()
    service = AssistantService(str(tmp_path / "settings"), str(tmp_path / "runtime"), host)
    try:
        saved = service.save_provider(
            {"kind": "llamacpp", "name": "Local", "base_url": f"http://127.0.0.1:{port}"}
        )

        async def run() -> None:
            first = service.start_chat(saved["provider"]["id"], "", "My favorite color is blue.", "req-1", "")
            assert first["ok"] is True
            for _ in range(50):
                if any(item.get("type") == "chat_done" for item in host.events):
                    break
                await asyncio.sleep(0.05)
            host.events.clear()
            second = service.start_chat(saved["provider"]["id"], "", "What color did I name?", "req-2", "")
            assert second["ok"] is True
            for _ in range(50):
                if any(item.get("type") == "chat_done" for item in host.events):
                    break
                await asyncio.sleep(0.05)
            await service.shutdown()

        asyncio.run(run())
    finally:
        server.shutdown()

    assert len(bodies) == 2
    assert bodies[0]["messages"][-1]["content"] == "My favorite color is blue."
    history = bodies[1]["messages"]
    assert any(item["content"] == "My favorite color is blue." for item in history)
    assert any(item["content"] == "blue" and item["role"] == "assistant" for item in history)
    assert history[-1]["content"] == "What color did I name?"
    assert bodies[1]["model"] == "qwen-test"


@pytest.mark.skipif(not os.environ.get("LLAMA_SERVER_URL"), reason="Set LLAMA_SERVER_URL to run against llama-server")
def test_live_llama_server() -> None:
    raw = os.environ["LLAMA_SERVER_URL"].strip().rstrip("/")
    key = os.environ.get("LLAMA_SERVER_API_KEY") or ""
    bare = raw[:-3] if raw.endswith("/v1") else raw
    with_v1 = bare if bare.endswith("/v1") else bare + "/v1"
    for base in (bare, with_v1):
        provider = {"kind": "llamacpp", "base_url": base, "api_key": key, "max_tokens": 32}
        models = list_models(provider)
        assert models, base
        text = "".join(
            iter_text(
                provider,
                [{"role": "user", "content": "Reply with the single word pong."}],
                "",
                threading.Event(),
            )
        )
        assert text.strip(), base


def test_public_https_keeps_the_tls_error_and_lan_hint_stays_on_lan() -> None:
    try:
        raise ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
    except ssl.SSLCertVerificationError as exc:
        public = _explain_llamacpp(exc, {"kind": "llamacpp", "base_url": "https://llama.example.com"})
    assert "SSLCertVerificationError" in str(public)
    assert "CERTIFICATE_VERIFY_FAILED" in str(public)
    assert "firewall" not in str(public).lower()

    refused = _explain_llamacpp(
        ConnectionRefusedError(111, "Connection refused"),
        {"kind": "llamacpp", "base_url": "http://192.168.1.20:8080"},
    )
    assert "firewall" in str(refused)
    public_refused = _explain_llamacpp(
        ConnectionRefusedError(111, "Connection refused"),
        {"kind": "llamacpp", "base_url": "https://llama.example.com"},
    )
    assert "firewall" in str(public_refused)


def test_models_name_list_is_accepted_when_data_is_missing() -> None:
    assert _ids_from_openai_payload(
        {"models": [{"name": "qwen3.8-flash-next"}], "object": "list"}
    ) == ["qwen3.8-flash-next"]
    assert _ids_from_openai_payload({"data": [{"id": "from-data"}], "models": [{"name": "other"}]}) == ["from-data"]


def test_https_context_uses_vendored_certifi_when_default_ca_is_missing(monkeypatch, tmp_path) -> None:
    from ai_assistant import http_util

    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "missing.pem"))
    monkeypatch.setenv("SSL_CERT_DIR", str(tmp_path / "missing-dir"))
    http_util._SSL_CONTEXT = None
    context = http_util.ssl_context()
    stats = context.cert_store_stats()
    assert stats["x509_ca"] > 10
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    bundle = http_util.ca_bundle()
    assert bundle.endswith("cacert.pem")
    assert os.path.isfile(bundle)
