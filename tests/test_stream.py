import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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


def test_custom_provider_streams_into_the_session(tmp_path) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = (
                b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
                b'data: {"choices":[{"delta":{"content":" Deck"}}]}\n\n'
                b"data: [DONE]\n\n"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            return None

    server, port = _serve(Handler)
    host = _Host()
    service = AssistantService(str(tmp_path / "settings"), str(tmp_path / "runtime"), host)
    try:
        saved = service.save_provider(
            {
                "kind": "custom",
                "name": "Local",
                "base_url": f"http://127.0.0.1:{port}/v1",
                "default_model": "test-model",
            }
        )

        async def run() -> None:
            result = service.start_chat(saved["provider"]["id"], "test-model", "Hi", "req-1", "")
            assert result["ok"] is True
            for _ in range(50):
                if any(item.get("type") == "chat_done" for item in host.events):
                    break
                await asyncio.sleep(0.05)
            await service.shutdown()

        asyncio.run(run())
    finally:
        server.shutdown()

    done = next(item for item in host.events if item.get("type") == "chat_done")
    assert done["text"] == "Hello Deck"
    assert done["messages"][-1]["content"] == "Hello Deck"
    assert done["messages"][-2]["content"] == "Hi"
    blob = json.dumps(host.events)
    assert "api_key" not in blob


def test_ollama_tags_and_chat(tmp_path) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = json.dumps({"models": [{"name": "llama3.2:latest"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802
            body = (
                b'{"message":{"role":"assistant","content":"Yo"},"done":false}\n'
                b'{"message":{"role":"assistant","content":""},"done":true}\n'
            )
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            return None

    server, port = _serve(Handler)
    host = _Host()
    service = AssistantService(str(tmp_path / "settings"), str(tmp_path / "runtime"), host)
    try:
        saved = service.save_provider(
            {"kind": "ollama", "name": "Ollama", "base_url": f"http://127.0.0.1:{port}"}
        )

        async def run() -> None:
            tested = await service.test_provider(saved["provider"]["id"])
            assert tested["ok"] is True
            assert tested["models"] == ["llama3.2:latest"]
            service.start_chat(saved["provider"]["id"], "llama3.2:latest", "Hey", "req-2", "Hades")
            for _ in range(50):
                if any(item.get("type") == "chat_done" for item in host.events):
                    break
                await asyncio.sleep(0.05)
            await service.shutdown()

        asyncio.run(run())
    finally:
        server.shutdown()

    done = next(item for item in host.events if item.get("type") == "chat_done")
    assert done["text"] == "Yo"
    assert "[Playing: Hades]" in done["messages"][0]["content"]
