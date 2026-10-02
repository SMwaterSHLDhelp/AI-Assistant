import os

import decky

from ai_assistant.redact import RedactFilter, redact
from ai_assistant.service import AssistantService

# Single event name the Quick Access panel and the settings page both listen for.
EVENT = "ai_assistant_event"


class Plugin:
    """Decky entrypoint. Methods are called from the frontend with @decky/api callable()."""

    service: AssistantService

    async def _migration(self) -> None:
        decky.logger.info("AI Assistant migration: nothing to move")

    async def _main(self) -> None:
        decky.logger.addFilter(RedactFilter())
        self.service = AssistantService(
            decky.DECKY_PLUGIN_SETTINGS_DIR,
            decky.DECKY_PLUGIN_RUNTIME_DIR,
            _DeckyHost(),
        )
        # Touch the settings directory so a fresh install gets mode 0700 immediately.
        os.makedirs(decky.DECKY_PLUGIN_SETTINGS_DIR, exist_ok=True)
        os.chmod(decky.DECKY_PLUGIN_SETTINGS_DIR, 0o700)
        decky.logger.info("AI Assistant ready")

    async def _unload(self) -> None:
        decky.logger.info("AI Assistant unloading")
        if hasattr(self, "service"):
            await self.service.shutdown()

    async def _uninstall(self) -> None:
        decky.logger.info("AI Assistant removing saved credentials and chats")
        if hasattr(self, "service"):
            self.service.store.delete_private_files()

    async def get_state(self) -> dict:
        # The settings page can open before _main finishes. Say so instead of raising.
        if not hasattr(self, "service"):
            return {"ok": False, "error": "AI Assistant is still starting."}
        return self._call(self.service.state)

    async def save_provider(self, provider: dict) -> dict:
        return self._call(self.service.save_provider, provider)

    async def delete_provider(self, provider_id: str) -> dict:
        return self._call(self.service.delete_provider, provider_id)

    async def save_settings(self, settings: dict) -> dict:
        return self._call(self.service.save_settings, settings)

    async def new_session(self) -> dict:
        return self._call(self.service.new_session)

    async def switch_session(self, session_id: str) -> dict:
        return self._call(self.service.switch_session, session_id)

    async def clear_session(self) -> dict:
        return self._call(self.service.clear_session)

    async def delete_session(self, session_id: str) -> dict:
        return self._call(self.service.delete_session, session_id)

    async def test_provider(self, provider_id: str) -> dict:
        return await self._acall(self.service.test_provider, provider_id)

    async def list_models(self, provider_id: str) -> dict:
        return await self._acall(self.service.list_models, provider_id)

    async def send_message(
        self,
        provider_id: str,
        model: str,
        content: str,
        request_id: str,
        about_game: str,
    ) -> dict:
        return self._call(self.service.start_chat, provider_id, model, content, request_id, about_game)

    async def cancel_chat(self, request_id: str) -> dict:
        return self._call(self.service.cancel_chat, request_id)

    async def start_oauth(self, provider_id: str, flow: str) -> dict:
        return self._call(self.service.start_oauth, provider_id, flow)

    async def cancel_oauth(self, provider_id: str) -> dict:
        return self._call(self.service.cancel_oauth, provider_id)

    async def oauth_status(self, provider_id: str) -> dict:
        return self._call(self.service.oauth_status, provider_id)

    def _call(self, fn, *args):  # type: ignore[no-untyped-def]
        try:
            return fn(*args)
        except Exception as exc:  # noqa: BLE001 - returned to the UI, never logged raw
            decky.logger.warning("%s failed: %s", getattr(fn, "__name__", "call"), redact(str(exc)))
            return {"ok": False, "error": redact(str(exc))}

    async def _acall(self, fn, *args):  # type: ignore[no-untyped-def]
        try:
            return await fn(*args)
        except Exception as exc:  # noqa: BLE001 - returned to the UI, never logged raw
            decky.logger.warning("%s failed: %s", getattr(fn, "__name__", "call"), redact(str(exc)))
            return {"ok": False, "error": redact(str(exc))}


class _DeckyHost:
    async def emit(self, event: str, payload: dict) -> None:
        await decky.emit(event, payload)

    def info(self, message: str, *args: object) -> None:
        decky.logger.info(message, *args)

    def warning(self, message: str, *args: object) -> None:
        decky.logger.warning(message, *args)
