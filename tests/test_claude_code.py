import asyncio
import importlib.util
import json
import os
import stat
import textwrap
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from ai_assistant.claude_code import (
    explain_failure,
    extract_setup_token,
    iter_stream_json,
    login_hints,
    normalize_model,
)
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


def _fake_claude(directory: Path) -> Path:
    path = directory / "claude"
    path.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json, os, sys
            args = sys.argv[1:]
            log = os.environ.get("CLAUDE_FAKE_LOG")
            if log and os.environ.get("ANTHROPIC_API_KEY"):
                with open(log, "a", encoding="utf-8") as handle:
                    handle.write("LEAKED\\n")
            if log:
                with open(log, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(args) + "\\n")
            if "setup-token" in args:
                sys.stdout.write("Visit https://claude.ai/oauth/authorize?foo=1\\n")
                sys.stdout.write("Code: ABCD-EFGH\\n")
                sys.stdout.write("sk-ant-oat01-abcdefghij\\n")
                sys.stdout.write("klmnopqrstuvwxyz012345\\n")
                sys.stdout.write("Store this token securely.\\n")
                sys.stdout.flush()
                raise SystemExit(0)
            if "--version" in args:
                print("claude 2.1.0")
                raise SystemExit(0)
            prompt = sys.stdin.read()
            model = args[args.index("--model") + 1] if "--model" in args else ""
            session = args[args.index("--resume") + 1] if "--resume" in args else "sess-new"
            if "RATE" in prompt:
                events = [
                    {"type": "system", "subtype": "api_retry", "error": "rate_limit", "session_id": session},
                    {"type": "result", "is_error": True, "subtype": "error", "session_id": session, "result": "rate limit"},
                ]
            else:
                events = [
                    {
                        "type": "stream_event",
                        "session_id": session,
                        "event": {"delta": {"type": "text_delta", "text": "Hi " + model}},
                    },
                    {"type": "result", "subtype": "success", "is_error": False, "session_id": session, "result": "Hi " + model},
                ]
            for event in events:
                print(json.dumps(event), flush=True)
            """
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _load_bridge():
    path = Path(__file__).resolve().parents[1] / "bridge" / "claude_bridge.py"
    spec = importlib.util.spec_from_file_location("claude_bridge", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_aliases_token_and_rate_limit_copy() -> None:
    assert normalize_model("Opus") == "opus"
    assert normalize_model("claude-haiku") == "haiku"
    assert normalize_model("claude-sonnet-4-5") == "claude-sonnet-4-5"
    wrapped = "prefix sk-ant-oat01-abcdefghij\nklmnopqrstuvwxyz012345\nStore this token securely.\n"
    assert extract_setup_token(wrapped) == "sk-ant-oat01-abcdefghijklmnopqrstuvwxyz012345"
    url, code = login_hints("Open https://claude.ai/login/x now\nCode: ABCD-EFGH\n")
    assert url == "https://claude.ai/login/x"
    assert code == "ABCD-EFGH"
    assert "rate or usage limit" in explain_failure("rate_limit", "ignored")
    assert "rate or usage limit" in explain_failure("", "HTTP 429 too many requests")
    meta: dict[str, str] = {}
    lines = [
        json.dumps(
            {
                "type": "stream_event",
                "session_id": "sess-1",
                "event": {"delta": {"type": "text_delta", "text": "Yo"}},
            }
        ),
        json.dumps({"type": "result", "session_id": "sess-1", "result": "Yo", "is_error": False}),
    ]
    assert "".join(iter_stream_json(iter(lines), meta)) == "Yo"
    assert meta["claude_session_id"] == "sess-1"


def test_local_claude_streams_and_resumes(tmp_path, monkeypatch) -> None:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _fake_claude(bindir)
    log = tmp_path / "argv.log"
    monkeypatch.setenv("PATH", f"{bindir}:/usr/bin:/bin")
    monkeypatch.setenv("CLAUDE_FAKE_LOG", str(log))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-matter")
    host = _Host()
    service = AssistantService(str(tmp_path / "settings"), str(tmp_path / "runtime"), host)
    saved = service.save_provider({"kind": "claude_code", "name": "Claude sub", "default_model": "sonnet"})

    async def run() -> None:
        tested = await service.test_provider(saved["provider"]["id"])
        assert tested["ok"] is True
        assert tested["models"] == ["sonnet", "opus", "haiku"]
        first = service.start_chat(saved["provider"]["id"], "claude-sonnet", "Hello", "req-1", "")
        assert first["ok"] is True
        for _ in range(50):
            if any(item.get("type") == "chat_done" for item in host.events):
                break
            await asyncio.sleep(0.05)
        host.events.clear()
        service.start_chat(saved["provider"]["id"], "sonnet", "Again", "req-2", "")
        for _ in range(50):
            if any(item.get("type") == "chat_done" for item in host.events):
                break
            await asyncio.sleep(0.05)
        await service.shutdown()

    asyncio.run(run())
    done = [item for item in host.events if item.get("type") == "chat_done"]
    assert done[-1]["text"] == "Hi sonnet"
    raw_log = log.read_text(encoding="utf-8")
    assert "LEAKED" not in raw_log
    recorded = [json.loads(line) for line in raw_log.splitlines()]
    chat_calls = [item for item in recorded if "--output-format" in item]
    assert chat_calls[0][chat_calls[0].index("--model") + 1] == "sonnet"
    assert "--bare" not in chat_calls[0]
    assert "--resume" not in chat_calls[0]
    assert chat_calls[1][chat_calls[1].index("--resume") + 1] == "sess-new"
    sessions = json.loads((tmp_path / "runtime" / "sessions.json").read_text(encoding="utf-8"))
    assert sessions["sessions"][0]["claude_session_id"] == "sess-new"
    service.store.clear_session()
    cleared = service.store.load_sessions()
    current = next(item for item in cleared["sessions"] if item["id"] == cleared["current_id"])
    assert "claude_session_id" not in current


def test_setup_token_saves_0600_and_hides_the_token(tmp_path, monkeypatch) -> None:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _fake_claude(bindir)
    monkeypatch.setenv("PATH", f"{bindir}:/usr/bin:/bin")
    host = _Host()
    service = AssistantService(str(tmp_path / "settings"), str(tmp_path / "runtime"), host)
    saved = service.save_provider({"kind": "claude_code", "name": "Claude sub"})

    async def run() -> None:
        started = service.start_oauth(saved["provider"]["id"], "setup-token")
        assert started["ok"] is True
        for _ in range(50):
            status = service.oauth_status(saved["provider"]["id"])
            if status.get("status") in {"success", "error"}:
                break
            await asyncio.sleep(0.05)
        await service.shutdown()

    asyncio.run(run())
    status = service.oauth_status(saved["provider"]["id"])
    assert status["status"] == "success"
    blob = json.dumps(host.events)
    assert "sk-ant-oat" not in blob
    assert "https://claude.ai/oauth/authorize?foo=1" in blob
    assert "ABCD-EFGH" in blob
    provider = service.store.get_provider(saved["provider"]["id"])
    assert provider["api_key"] == "sk-ant-oat01-abcdefghijklmnopqrstuvwxyz012345"
    mode = stat.S_IMODE(os.stat(service.store.credentials_path).st_mode)
    assert mode == 0o600
    assert "sk-ant-oat" not in json.dumps(service.state())


def test_rate_limit_is_explicit(tmp_path, monkeypatch) -> None:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _fake_claude(bindir)
    monkeypatch.setenv("PATH", f"{bindir}:/usr/bin:/bin")
    host = _Host()
    service = AssistantService(str(tmp_path / "settings"), str(tmp_path / "runtime"), host)
    saved = service.save_provider({"kind": "claude_code", "name": "Claude sub", "default_model": "haiku"})

    async def run() -> None:
        service.start_chat(saved["provider"]["id"], "haiku", "RATE please", "req-r", "")
        for _ in range(50):
            if any(item.get("type") == "chat_error" for item in host.events):
                break
            await asyncio.sleep(0.05)
        await service.shutdown()

    asyncio.run(run())
    error = next(item for item in host.events if item.get("type") == "chat_error")
    assert "rate or usage limit" in error["error"]


def test_bridge_rejects_a_bad_secret_and_streams(tmp_path, monkeypatch) -> None:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    binary = _fake_claude(bindir)
    monkeypatch.setenv("CLAUDE_FAKE_LOG", str(tmp_path / "bridge-argv.log"))
    bridge = _load_bridge()
    secret = "bridge-secret-value"
    server = ThreadingHTTPServer(("127.0.0.1", 0), bridge.make_handler(secret, str(binary)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    host = _Host()
    service = AssistantService(str(tmp_path / "settings"), str(tmp_path / "runtime"), host)
    try:
        rejected = service.save_provider(
            {
                "kind": "claude_code",
                "name": "Remote",
                "base_url": f"http://127.0.0.1:{port}",
                "api_key": "wrong-secret-value",
                "default_model": "opus",
            }
        )

        async def run() -> None:
            failed = await service.test_provider(rejected["provider"]["id"])
            assert failed["ok"] is False
            assert "shared secret" in (failed.get("error") or "")
            service.save_provider(
                {
                    "id": rejected["provider"]["id"],
                    "kind": "claude_code",
                    "name": "Remote",
                    "base_url": f"http://127.0.0.1:{port}",
                    "api_key": secret,
                    "default_model": "opus",
                }
            )
            tested = await service.test_provider(rejected["provider"]["id"])
            assert tested["ok"] is True
            assert tested["models"] == ["sonnet", "opus", "haiku"]
            service.start_chat(rejected["provider"]["id"], "opus", "Hello bridge", "req-b", "")
            for _ in range(50):
                if any(item.get("type") == "chat_done" for item in host.events):
                    break
                await asyncio.sleep(0.05)
            await service.shutdown()
        asyncio.run(run())
    finally:
        server.shutdown()
    done = next(item for item in host.events if item.get("type") == "chat_done")
    assert done["text"] == "Hi opus"
    recorded = json.loads((tmp_path / "bridge-argv.log").read_text(encoding="utf-8").splitlines()[-1])
    assert "--bare" not in recorded
    assert "stream-json" in recorded
