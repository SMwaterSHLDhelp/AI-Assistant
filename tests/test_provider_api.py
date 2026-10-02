"""The Decky callables the settings page uses to add, update, and delete providers."""

import asyncio
import logging
import os
import stat
import sys
import types
from pathlib import Path


def _load_plugin(tmp_path: Path):
    fake = types.ModuleType("decky")
    fake.logger = logging.getLogger("decky-test")
    fake.DECKY_PLUGIN_SETTINGS_DIR = str(tmp_path / "settings")
    fake.DECKY_PLUGIN_RUNTIME_DIR = str(tmp_path / "runtime")

    async def emit(event: str, payload: dict) -> None:
        return None

    fake.emit = emit
    sys.modules["decky"] = fake
    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)
    if "main" in sys.modules:
        del sys.modules["main"]
    import main

    return main


def test_get_state_before_startup_names_the_real_error(tmp_path) -> None:
    main = _load_plugin(tmp_path)

    async def run() -> None:
        plugin = main.Plugin()
        result = await plugin.get_state()
        assert result["ok"] is False
        assert result["error"] == "Deckling is still starting."

    asyncio.run(run())


def test_plugin_callables_add_update_and_delete_a_provider(tmp_path) -> None:
    main = _load_plugin(tmp_path)

    async def run() -> None:
        plugin = main.Plugin()
        await plugin._main()
        created = await plugin.save_provider(
            {
                "kind": "llamacpp",
                "name": "PC",
                "base_url": "http://192.168.1.20:8080",
                "default_model": "",
                "max_tokens": 256,
                "api_key": "secret-key",
                "oauth_client_id": "",
                "oauth_client_secret": None,
            }
        )
        assert created["ok"] is True
        provider = created["provider"]
        assert provider["kind"] == "llamacpp"
        assert provider["base_url"] == "http://192.168.1.20:8080"
        assert provider["has_api_key"] is True
        assert "api_key" not in provider
        assert "secret-key" not in str(created)

        updated = await plugin.save_provider(
            {
                "id": provider["id"],
                "kind": "llamacpp",
                "name": "LAN llama",
                "base_url": "http://192.168.1.20:8080/v1",
                "default_model": "qwen",
                "max_tokens": 512,
                "api_key": None,
                "oauth_client_id": "",
                "oauth_client_secret": None,
            }
        )
        assert updated["ok"] is True
        assert updated["provider"]["name"] == "LAN llama"
        assert updated["provider"]["base_url"] == "http://192.168.1.20:8080/v1"
        assert updated["provider"]["default_model"] == "qwen"
        assert updated["provider"]["max_tokens"] == 512
        assert updated["provider"]["has_api_key"] is True

        missing = await plugin.save_provider(
            {"id": "missing", "kind": "ollama", "name": "Nope", "base_url": "http://127.0.0.1:11434"}
        )
        assert missing["ok"] is False
        assert missing["error"]

        unknown = await plugin.save_provider({"kind": "not-a-kind", "name": "Bad"})
        assert unknown["ok"] is False
        assert "Unknown provider type" in unknown["error"]

        deleted = await plugin.delete_provider(provider["id"])
        assert deleted["ok"] is True
        state = await plugin.get_state()
        assert state["ok"] is True
        assert state["catalog"]
        assert all(item["kind"] != "" for item in state["catalog"])
        assert all(item["id"] != provider["id"] for item in state["providers"])
        await plugin._unload()

    asyncio.run(run())


def test_legacy_ai_assistant_files_are_copied_once(tmp_path) -> None:
    main = _load_plugin(tmp_path)
    legacy = tmp_path / "AI Assistant"
    legacy.mkdir()
    (legacy / "credentials.json").write_text('{"providers":[]}\n', encoding="utf-8")
    (legacy / "sessions.json").write_text('{"sessions":[]}\n', encoding="utf-8")

    async def run() -> None:
        plugin = main.Plugin()
        await plugin._main()
        settings = tmp_path / "settings" / "credentials.json"
        runtime = tmp_path / "runtime" / "sessions.json"
        assert settings.read_text(encoding="utf-8") == '{"providers":[]}\n'
        assert runtime.read_text(encoding="utf-8") == '{"sessions":[]}\n'
        assert stat.S_IMODE(settings.stat().st_mode) == 0o600
        assert stat.S_IMODE(runtime.stat().st_mode) == 0o600
        assert stat.S_IMODE((tmp_path / "settings").stat().st_mode) == 0o700
        settings.write_text('{"kept":true}\n', encoding="utf-8")
        await plugin._migration()
        assert settings.read_text(encoding="utf-8") == '{"kept":true}\n'
        await plugin._unload()

    asyncio.run(run())


def test_legacy_copy_skips_a_path_that_is_itself(tmp_path) -> None:
    main = _load_plugin(tmp_path)
    dest = tmp_path / "settings"
    dest.mkdir()
    source = dest / "credentials.json"
    source.write_text("{}\n", encoding="utf-8")
    # Point the legacy folder at the destination itself.
    os.symlink(dest, tmp_path / "AI Assistant", target_is_directory=True)
    copied = main._copy_if_missing(str(dest), "credentials.json", lambda _message: None)
    assert copied is False
    assert source.read_text(encoding="utf-8") == "{}\n"
