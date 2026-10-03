import os
import shutil

import decky

from ai_assistant.redact import RedactFilter, redact
from ai_assistant.service import AssistantService

# Single event name the Quick Access panel and the settings page both listen for.
EVENT = "deckling_event"
LEGACY_NAME = "AI Assistant"


class Plugin:
    """Decky entrypoint. Methods are called from the frontend with @decky/api callable()."""

    service: AssistantService

    async def _migration(self) -> None:
        migrate_legacy(decky.DECKY_PLUGIN_SETTINGS_DIR, decky.DECKY_PLUGIN_RUNTIME_DIR, decky.logger.info)

    async def _main(self) -> None:
        decky.logger.addFilter(RedactFilter())
        # Copy the old plugin's files before the service reads them. _migration does not run every boot.
        migrate_legacy(decky.DECKY_PLUGIN_SETTINGS_DIR, decky.DECKY_PLUGIN_RUNTIME_DIR, decky.logger.info)
        self.service = AssistantService(
            decky.DECKY_PLUGIN_SETTINGS_DIR,
            decky.DECKY_PLUGIN_RUNTIME_DIR,
            _DeckyHost(),
        )
        # Touch the settings directory so a fresh install gets mode 0700 immediately.
        os.makedirs(decky.DECKY_PLUGIN_SETTINGS_DIR, exist_ok=True)
        os.chmod(decky.DECKY_PLUGIN_SETTINGS_DIR, 0o700)
        decky.logger.info("Deckling ready")

    async def _unload(self) -> None:
        decky.logger.info("Deckling unloading")
        if hasattr(self, "service"):
            await self.service.shutdown()

    async def _uninstall(self) -> None:
        decky.logger.info("Deckling removing saved credentials and chats")
        if hasattr(self, "service"):
            self.service.store.delete_private_files()

    async def get_state(self) -> dict:
        # The settings page can open before _main finishes. Say so instead of raising.
        if not hasattr(self, "service"):
            return {"ok": False, "error": "Deckling is still starting."}
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

    async def set_game_context(self, snapshot: dict) -> dict:
        return self._call(self.service.set_game_context, snapshot)

    async def save_context(self, settings: dict) -> dict:
        return self._call(self.service.save_context, settings)

    async def save_hearing(self, settings: dict) -> dict:
        return self._call(self.service.save_hearing, settings)

    async def push_to_talk(self) -> dict:
        return self._call(self.service.push_to_talk)

    async def stop_listening(self) -> dict:
        return self._call(self.service.stop_listening)

    async def set_hearing_activity(self, game_running: bool, sleeping: bool) -> dict:
        return self._call(self.service.set_hearing_activity, game_running, sleeping)

    async def save_voice(self, settings: dict) -> dict:
        return self._call(self.service.save_voice, settings)

    async def test_voice(self) -> dict:
        return await self._acall(self.service.test_voice)

    async def stop_speaking(self) -> dict:
        return self._call(self.service.stop_speaking)

    async def retry_kitten(self) -> dict:
        return await self._acall(self.service.retry_kitten)

    async def look_at_screen(
        self,
        provider_id: str,
        model: str,
        question: str,
        request_id: str,
        game: str,
        image_b64: str,
        qam_hidden: bool,
    ) -> dict:
        return self._call(
            self.service.look_at_screen,
            provider_id,
            model,
            question,
            request_id,
            game,
            image_b64,
            qam_hidden,
        )

    async def save_last_screenshot(self) -> dict:
        return self._call(self.service.save_last_screenshot)

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


def migrate_legacy(settings_dir: str, runtime_dir: str, log) -> None:
    """Copy credentials and chats from the previous plugin folders when Deckling's copies are missing."""
    copied_settings = _copy_if_missing(settings_dir, "credentials.json", log)
    copied_runtime = _copy_if_missing(runtime_dir, "sessions.json", log)
    if not copied_settings and not copied_runtime:
        log("Deckling migration: nothing to copy from the previous install")


def _copy_if_missing(dest_dir: str, filename: str, log) -> bool:
    dest = os.path.join(dest_dir, filename)
    if os.path.exists(dest):
        return False
    parent = os.path.dirname(os.path.abspath(dest_dir))
    source = os.path.join(parent, LEGACY_NAME, filename)
    if not os.path.isfile(source):
        return False
    if os.path.realpath(source) == os.path.realpath(dest):
        return False
    os.makedirs(dest_dir, exist_ok=True)
    os.chmod(dest_dir, 0o700)
    shutil.copy2(source, dest)
    os.chmod(dest, 0o600)
    log(f"Deckling copied {filename} from the previous install")
    return True


class _DeckyHost:
    async def emit(self, event: str, payload: dict) -> None:
        await decky.emit(event, payload)

    def info(self, message: str, *args: object) -> None:
        decky.logger.info(message, *args)

    def warning(self, message: str, *args: object) -> None:
        decky.logger.warning(message, *args)
