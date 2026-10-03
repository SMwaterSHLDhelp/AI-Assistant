"""Saving a provider must not wait on a model list, for every provider type."""

import asyncio
from pathlib import Path

from ai_assistant import providers
from ai_assistant.catalog import KINDS
from ai_assistant.service import AssistantService


def _minimum_payload(kind: str) -> dict:
    info = KINDS[kind]
    payload: dict = {"kind": kind, "name": info.label, "default_model": ""}
    if kind == "custom":
        payload["base_url"] = "http://127.0.0.1:9/v1"
    elif info.default_base_url:
        payload["base_url"] = info.default_base_url
    if info.auth == "required":
        payload["api_key"] = "test-key-not-a-secret"
    return payload


def test_each_provider_saves_with_an_empty_model_then_lists_models(tmp_path, monkeypatch) -> None:
    service = AssistantService(str(tmp_path / "settings"), str(tmp_path / "runtime"))
    seen: list[str] = []

    def fake_list(record: dict) -> list[str]:
        assert record.get("default_model", "") == ""
        seen.append(str(record.get("kind")))
        return [f"{record.get('kind')}-a", f"{record.get('kind')}-b"]

    monkeypatch.setattr(providers, "list_models", fake_list)
    for kind in KINDS:
        saved = service.save_provider(_minimum_payload(kind))
        assert saved["ok"] is True, kind
        provider = saved["provider"]
        assert provider["default_model"] == "", kind
        assert provider["id"]
        listed = asyncio.run(service.list_models(provider["id"]))
        assert listed["ok"] is True, kind
        assert listed["models"] == [f"{kind}-a", f"{kind}-b"]
    assert seen == list(KINDS)


def test_model_list_failure_is_logged_and_does_not_drop_the_provider(tmp_path, monkeypatch) -> None:
    warnings: list[str] = []

    class Host:
        async def emit(self, _event: str, _payload: dict) -> None:
            return None

        def info(self, _message: str, *_args: object) -> None:
            return None

        def warning(self, message: str, *args: object) -> None:
            warnings.append(message % args if args else message)

    service = AssistantService(str(tmp_path / "settings"), str(tmp_path / "runtime"), Host())

    def explode(_record: dict) -> list[str]:
        raise ValueError("connection refused")

    monkeypatch.setattr(providers, "list_models", explode)
    saved = service.save_provider(_minimum_payload("ollama"))
    listed = asyncio.run(service.list_models(saved["provider"]["id"]))
    assert saved["ok"] is True
    assert service.store.get_provider(saved["provider"]["id"])["name"] == "Ollama"
    assert listed["ok"] is False
    assert "connection refused" in listed["error"]
    assert any("Model list failed" in line and "connection refused" in line for line in warnings)


def test_settings_and_provider_screens_keep_actions_on_click() -> None:
    root = Path("src")
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.tsx"))
    assert "Focusable" not in source
    route = (root / "settings" / "SettingsRoute.tsx").read_text(encoding="utf-8")
    editor = (root / "settings" / "ProviderEditor.tsx").read_text(encoding="utf-8")
    index = (root / "index.tsx").read_text(encoding="utf-8")
    assert "SidebarNavigation" in route
    assert "mountPageShell" in route
    assert "SettingsRoute" in index
    assert "DialogBody" in editor or "SettingsDialog" in editor
    assert "DialogButton" in editor
    assert "Save provider" in editor
    assert "onActivate" not in source
