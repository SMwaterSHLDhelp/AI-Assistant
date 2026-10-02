import json
import os
import stat

import pytest

from ai_assistant.store import Store, public_provider


def test_credentials_are_mode_0600(tmp_path) -> None:
    store = Store(str(tmp_path / "settings"), str(tmp_path / "runtime"))
    record = store.upsert_provider(
        {
            "kind": "openai",
            "name": "Work",
            "api_key": "sk-test-secret-value",
            "default_model": "gpt-4o-mini",
        }
    )
    cred_mode = stat.S_IMODE(os.stat(store.credentials_path).st_mode)
    dir_mode = stat.S_IMODE(os.stat(store.settings_dir).st_mode)
    assert cred_mode == 0o600
    assert dir_mode == 0o700
    on_disk = json.loads(store.credentials_path and open(store.credentials_path, encoding="utf-8").read())
    assert on_disk["providers"][0]["api_key"] == "sk-test-secret-value"
    public = public_provider(record)
    assert "api_key" not in public
    assert public["has_api_key"] is True
    assert public["api_key_last4"] == "alue"
    assert "sk-test-secret-value" not in json.dumps(public)


def test_blank_secret_keeps_existing_key(tmp_path) -> None:
    store = Store(str(tmp_path / "settings"), str(tmp_path / "runtime"))
    created = store.upsert_provider({"kind": "anthropic", "name": "Claude", "api_key": "sk-ant-originalkey"})
    updated = store.upsert_provider({"id": created["id"], "kind": "anthropic", "name": "Claude", "api_key": None})
    assert updated["api_key"] == "sk-ant-originalkey"
    cleared = store.upsert_provider({"id": created["id"], "kind": "anthropic", "name": "Claude", "api_key": ""})
    assert cleared["api_key"] == ""


def test_rejects_non_http_urls(tmp_path) -> None:
    store = Store(str(tmp_path / "settings"), str(tmp_path / "runtime"))
    with pytest.raises(ValueError):
        store.upsert_provider({"kind": "custom", "name": "Bad", "base_url": "file:///etc/passwd"})
    with pytest.raises(ValueError):
        store.upsert_provider(
            {"kind": "ollama", "name": "Local", "base_url": "http://user:pass@127.0.0.1:11434"}
        )


def test_session_round_trip(tmp_path) -> None:
    store = Store(str(tmp_path / "settings"), str(tmp_path / "runtime"))
    first = store.new_session()
    store.append_message(first["id"], "user", "Hello there")
    second = store.new_session()
    store.switch_session(first["id"])
    data = store.load_sessions()
    assert data["current_id"] == first["id"]
    current = next(item for item in data["sessions"] if item["id"] == first["id"])
    assert current["messages"][0]["content"] == "Hello there"
    assert current["title"].startswith("Hello")
    assert second["id"] != first["id"]
    session_mode = stat.S_IMODE(os.stat(store.sessions_path).st_mode)
    assert session_mode == 0o600
