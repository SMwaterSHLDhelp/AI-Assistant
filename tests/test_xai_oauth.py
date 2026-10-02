import asyncio
import json

from ai_assistant.http_util import HttpError
from ai_assistant.oauth import (
    XAI_CLIENT_ID,
    XAI_DEVICE_URL,
    XAI_TOKEN_URL,
    refresh_access_token,
    xai_device_poll,
    xai_device_start,
)
from ai_assistant.providers import list_models
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


def test_xai_device_flow_uses_the_public_client(monkeypatch) -> None:
    captured: dict = {}

    def fake(method, url, **kwargs):  # type: ignore[no-untyped-def]
        captured["method"] = method
        captured["url"] = url
        captured["form"] = kwargs.get("form")
        return {
            "device_code": "device-secret",
            "user_code": "WXYZ-1234",
            "verification_uri": "https://auth.x.ai/device",
            "interval": 5,
            "expires_in": 600,
        }

    monkeypatch.setattr("ai_assistant.oauth.request_json", fake)
    started = xai_device_start()
    assert captured["method"] == "POST"
    assert captured["url"] == XAI_DEVICE_URL
    assert captured["form"]["client_id"] == XAI_CLIENT_ID
    assert "client_secret" not in captured["form"]
    assert "api:access" in captured["form"]["scope"]
    assert "grok-cli:access" in captured["form"]["scope"]
    assert started["user_code"] == "WXYZ-1234"
    assert started["verification_url"] == "https://auth.x.ai/device"
    assert "device-secret" not in json.dumps({key: started[key] for key in ("user_code", "verification_url", "message")})


def test_xai_poll_and_refresh_send_no_secret(monkeypatch) -> None:
    def pending(method, url, **kwargs):  # type: ignore[no-untyped-def]
        raise HttpError(400, 'HTTP 400: {"error":"authorization_pending"}')

    monkeypatch.setattr("ai_assistant.oauth.request_json", pending)
    assert xai_device_poll("device-secret") is None

    def success(method, url, **kwargs):  # type: ignore[no-untyped-def]
        assert url == XAI_TOKEN_URL
        assert kwargs["form"]["client_id"] == XAI_CLIENT_ID
        assert kwargs["form"]["grant_type"].endswith("device_code")
        assert "client_secret" not in kwargs["form"]
        return {"access_token": "access-1", "refresh_token": "refresh-1", "expires_in": 120}

    monkeypatch.setattr("ai_assistant.oauth.request_json", success)
    tokens = xai_device_poll("device-secret")
    assert tokens is not None
    assert tokens["access_token"] == "access-1"

    def refresh(method, url, **kwargs):  # type: ignore[no-untyped-def]
        assert url == XAI_TOKEN_URL
        form = kwargs["form"]
        assert form["grant_type"] == "refresh_token"
        assert form["client_id"] == XAI_CLIENT_ID
        assert form["refresh_token"] == "refresh-1"
        assert "client_secret" not in form
        return {"access_token": "access-2", "expires_in": 120}

    monkeypatch.setattr("ai_assistant.oauth.request_json", refresh)
    fields = refresh_access_token(
        {
            "kind": "xai",
            "oauth_refresh_token": "refresh-1",
            "oauth_expires_at": 0,
            "oauth_client_secret": "not-used",
        }
    )
    assert fields is not None
    assert fields["access_token"] == "access-2"
    assert fields["refresh_token"] == "refresh-1"


def test_xai_lists_models_from_the_official_api(monkeypatch) -> None:
    def fake(method, url, **kwargs):  # type: ignore[no-untyped-def]
        assert method == "GET"
        assert url == "https://api.x.ai/v1/models"
        assert kwargs["headers"]["Authorization"] == "Bearer xai-test-key-value"
        return {"data": [{"id": "grok-4.7"}, {"id": "grok-4"}]}

    monkeypatch.setattr("ai_assistant.providers.request_json", fake)
    models = list_models({"kind": "xai", "base_url": "https://api.x.ai/v1", "api_key": "xai-test-key-value"})
    assert models == ["grok-4", "grok-4.7"]


def test_xai_device_login_stores_tokens_without_showing_them(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "ai_assistant.oauth.xai_device_start",
        lambda: {
            "device_code": "device-secret",
            "user_code": "WXYZ-1234",
            "verification_url": "https://auth.x.ai/device",
            "interval": 5,
            "expires_in": 60,
            "message": "Open the verification page and enter the code.",
        },
    )
    monkeypatch.setattr(
        "ai_assistant.oauth.xai_device_poll",
        lambda device_code: {
            "access_token": "access-token-value",
            "refresh_token": "refresh-token-value",
            "expires_at": 9_999_999_999,
        },
    )
    host = _Host()
    service = AssistantService(str(tmp_path / "settings"), str(tmp_path / "runtime"), host)
    saved = service.save_provider({"kind": "xai", "name": "Grok"})

    async def run() -> None:
        started = service.start_oauth(saved["provider"]["id"], "device")
        assert started["ok"] is True
        for _ in range(50):
            status = service.oauth_status(saved["provider"]["id"])
            if status.get("status") in {"success", "error"}:
                break
            await asyncio.sleep(0.05)
        await service.shutdown()

    asyncio.run(run())
    assert service.oauth_status(saved["provider"]["id"])["status"] == "success"
    stored = service.store.get_provider(saved["provider"]["id"])
    assert stored["oauth_access_token"] == "access-token-value"
    public = json.dumps(service.state())
    events = json.dumps(host.events)
    assert "access-token-value" not in public
    assert "access-token-value" not in events
    assert "device-secret" not in events
    assert "WXYZ-1234" in events
