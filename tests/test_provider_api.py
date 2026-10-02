"""The Decky callables the settings page uses to add, update, and delete providers."""

import asyncio
import logging
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
        assert result["error"] == "AI Assistant is still starting."

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
