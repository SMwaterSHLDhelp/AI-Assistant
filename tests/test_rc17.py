"""Photo banner, spoken-text cleanup, and stop-talking for rc.17."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ai_assistant.hearing import HearingEngine
from ai_assistant.screen import CaptureError
from ai_assistant.service import AssistantService
from ai_assistant.voice import CODE_NOTE, LINK_NOTE, for_speech
from ai_assistant.web_chat import ScreenCapture, iter_with_tools, text_tool_calls, tool_spec
from test_voice_screen import FakeProc


def test_for_speech_keeps_words_and_the_full_reply() -> None:
    spoken = for_speech(
        "See **Malenia**.\n\n"
        "- Dodge left\n"
        "- Hit after the slam\n\n"
        "Guide: https://wiki.example/malenia and `R1`.\n\n"
        "```\nprint('hi')\n```\n\n"
        "e.g. a spear. 🙂"
    )
    assert "*" not in spoken
    assert "#" not in spoken
    assert "`" not in spoken
    assert "http" not in spoken
    assert "🙂" not in spoken
    assert "Dodge left." in spoken
    assert "Hit after the slam." in spoken
    assert "for example a spear." in spoken
    assert CODE_NOTE in spoken
    assert LINK_NOTE in spoken
    assert "the rest is in the chat" not in spoken.lower()
    long = for_speech(("Wait. " * 80).strip())
    assert long.count("Wait.") == 80


def test_stop_drops_sentences_that_have_not_started(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    engine = AssistantService(str(tmp_path / "settings"), str(tmp_path / "runtime")).voice
    engine.store.update_voice({"voice_enabled": True})
    spoken: list[bytes] = []

    def popen(args, **kwargs):
        proc = FakeProc(args)
        proc.kwargs_env = kwargs.get("env") or {}
        if args and args[0] == "paplay":

            def wait(timeout=None):  # noqa: ARG001
                engine._stop.set()
                return 0

            proc.wait = wait  # type: ignore[method-assign]
        original = proc.stdin.write

        def write(data):
            spoken.append(bytes(data))
            return original(data)

        proc.stdin.write = write  # type: ignore[method-assign]
        return proc

    engine.fetch = lambda _url, dest: __import__("pathlib").Path(dest).write_bytes(b"x")
    engine.popen = popen
    engine.which = lambda name: "/usr/bin/paplay" if name == "paplay" else None
    engine._ensure_piper = lambda: "/tmp/piper"  # type: ignore[method-assign]
    engine._ensure_piper_voice = lambda _voice: ("/tmp/voice.onnx", "/tmp/voice.onnx.json")  # type: ignore[method-assign]
    monkeypatch.setattr("ai_assistant.voice._sample_rate", lambda _path: 22050)
    result = engine.speak_blocking("First sentence. Second sentence.", force=True)
    assert result.get("stopped") is True
    assert spoken == [b"First sentence."]
    assert engine.is_speaking() is False


def test_push_to_talk_and_voice_stop_do_not_start_a_recording(tmp_path) -> None:
    service = AssistantService(str(tmp_path / "settings"), str(tmp_path / "runtime"))
    started: list[str] = []
    service.hearing.begin_ptt = lambda: started.append("ptt")  # type: ignore[method-assign]
    service.voice._speaking = True
    stopped = service.push_to_talk()
    assert stopped["ok"] is True
    assert stopped["stopped"] is True
    assert started == []
    service.voice._speaking = True
    service._hearing_command("stop_talking", "stop")
    assert service.voice.is_speaking() is False
    _sessions, current = service.store.ensure_session()
    assert all(item.get("content") != "Cancelled." for item in current["messages"])


def test_echo_while_speaking_is_not_a_message(tmp_path) -> None:
    commands: list[tuple[str, str]] = []
    engine = HearingEngine(
        AssistantService(str(tmp_path / "settings"), str(tmp_path / "runtime")).store,
        on_command=lambda action, text: commands.append((action, text)),
        speaking=lambda: True,
    )
    engine.update({"wake_enabled": True})
    assert engine.dispatch("the glowing door is on the left") == "ignore"
    assert engine.dispatch("shut up") == "stop_talking"
    assert commands == [("stop_talking", "shut up")]
    assert engine.public()["wake_enabled"] is True
    assert engine.public()["phase"] == "listening"


def test_screen_tool_is_gated_and_attaches_jpeg(tmp_path) -> None:
    names = {spec["name"] for spec in tool_spec()}
    assert "look_at_screen" not in names
    assert "look_at_screen" in {spec["name"] for spec in tool_spec(include_screen=True)}
    hidden = text_tool_calls('<tool_call>{"name":"look_at_screen","arguments":{}}</tool_call>')
    assert hidden == []
    grabbed: list[int] = []

    def grab(_arguments):
        grabbed.append(1)
        return json.dumps({"ok": True}), b"\xff\xd8jpeg"

    seen: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length))
            seen.append(payload)
            fed = any(
                item.get("role") == "tool" or "screenshot you just took" in json.dumps(item.get("content"))
                for item in payload.get("messages") or []
            )
            if fed:
                raw = b'data: {"choices":[{"delta":{"content":"A red door."}}]}\n\ndata: [DONE]\n\n'
            else:
                body = '<tool_call>{"name":"look_at_screen","arguments":{}}</tool_call>'
                raw = (
                    b'data: {"choices":[{"delta":{"content":'
                    + json.dumps(body).encode()
                    + b"}}]}\n\ndata: [DONE]\n\n"
                )
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, fmt: str, *args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    provider = {"kind": "llamacpp", "base_url": f"http://127.0.0.1:{server.server_address[1]}", "api_key": ""}
    try:
        from ai_assistant.web import WebClient

        client = WebClient(str(tmp_path), sleep=lambda _seconds: None)
        text = "".join(
            iter_with_tools(
                provider,
                [{"role": "user", "content": "what is on screen"}],
                "qwen",
                threading.Event(),
                client,
                screen=ScreenCapture(grab),
                include_web=False,
            )
        )
    finally:
        server.shutdown()
    assert text == "A red door."
    assert grabbed == [1]
    blob = json.dumps(seen[-1])
    assert "data:image/jpeg;base64," in blob
    assert "look_at_screen" in json.dumps(seen[1]["tools"])


def test_model_grab_announces_before_capture_and_respects_the_toggle(tmp_path) -> None:
    notes: list[str] = []
    service = AssistantService(str(tmp_path / "settings"), str(tmp_path / "runtime"))
    service.screen_grabbers = [lambda _context: (_ for _ in ()).throw(CaptureError("no display"))]
    text, image = service._grab_for_model(notes.append)
    assert notes == ["Taking photo"]
    assert image is None
    assert "no display" in text
    service.save_voice({"screen_capture": False})
    notes.clear()
    refused, shot = service._grab_for_model(notes.append)
    assert notes == []
    assert shot is None
    assert "turned off" in refused
    provider = {"kind": "openai", "id": "cloud", "base_url": "https://example.invalid"}
    assert service._offer_screen_tool(provider, "gpt-4o") is False
    service.save_voice({"screen_capture": True})
    assert service._offer_screen_tool(provider, "gpt-4o") is True
    assert service._offer_screen_tool(provider, "llama3:latest") is False
