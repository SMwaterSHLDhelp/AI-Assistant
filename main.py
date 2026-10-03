import logging
import os
import shutil
import traceback

import decky

from ai_assistant.diagnostics import diagnostics_path, remember, snapshot, write_report
from ai_assistant.redact import RedactFilter, redact
from ai_assistant.service import AssistantService

# Single event name the Quick Access panel and the settings page both listen for.
EVENT = "deckling_event"
LEGACY_NAME = "AI Assistant"
VERSION = "0.1.0-rc.11"


class Plugin:
    """Decky entrypoint. Methods are called from the frontend with @decky/api callable()."""

    service: AssistantService
    _boot_error: str = ""

    async def _migration(self) -> None:
        # Decky runs this before the method socket exists. An exception here
        # makes the loader exit the process, and every later call times out.
        try:
            migrate_legacy(decky.DECKY_PLUGIN_SETTINGS_DIR, decky.DECKY_PLUGIN_RUNTIME_DIR, decky.logger.info)
        except Exception as exc:  # noqa: BLE001 - stay up so health can report this
            self._fail("Deckling could not migrate the previous install.", exc)

    async def _main(self) -> None:
        self._boot_error = ""
        decky.logger.addFilter(RedactFilter())
        _install_log_ring()
        try:
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
        except Exception as exc:  # noqa: BLE001 - keep the process up so the UI can show this
            self._fail("Deckling failed to start.", exc)

    def _fail(self, summary: str, exc: BaseException) -> None:
        detail = redact(traceback.format_exc())
        self._boot_error = redact(str(exc)) or summary
        decky.logger.error("%s %s", summary, self._boot_error)
        remember(self._boot_error)
        header = f"Deckling {VERSION} failed to start\n{summary}\n{self._boot_error}"
        for path in _boot_paths():
            try:
                write_report(path, [detail], header)
            except Exception:
                decky.logger.warning("Could not write the startup error to %s", path)

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
        blocked = self._blocked()
        if blocked:
            return blocked
        return self._call("state")

    async def health(self) -> dict:
        blocked = self._blocked()
        if blocked:
            return {"ok": False, "version": VERSION, "error": blocked["error"]}
        return {"ok": True, "version": VERSION, "error": ""}

    async def diagnostics(self) -> dict:
        return {
            "ok": True,
            "version": VERSION,
            "error": self._boot_error,
            "lines": snapshot(),
        }

    async def write_diagnostics(self) -> dict:
        path = diagnostics_path()
        header = f"Deckling {VERSION}\n{self._boot_error or 'backend ok'}"
        try:
            write_report(path, snapshot(), header)
        except Exception as exc:  # noqa: BLE001 - returned to the UI, never logged raw
            message = redact(str(exc)) or "Could not write the diagnostics file."
            decky.logger.warning("diagnostics file failed: %s", message)
            return {"ok": False, "error": message}
        decky.logger.info("Wrote diagnostics to %s", path)
        return {"ok": True, "path": path}

    async def log_client(self, message: str) -> dict:
        text = redact(str(message or "")).replace("\n", " ").strip()[:400]
        if text:
            decky.logger.warning("UI: %s", text)
        return {"ok": True}

    async def save_provider(self, provider: dict) -> dict:
        return self._call("save_provider", provider)

    async def delete_provider(self, provider_id: str) -> dict:
        return self._call("delete_provider", provider_id)

    async def save_settings(self, settings: dict) -> dict:
        return self._call("save_settings", settings)

    async def new_session(self) -> dict:
        return self._call("new_session")

    async def switch_session(self, session_id: str) -> dict:
        return self._call("switch_session", session_id)

    async def clear_session(self) -> dict:
        return self._call("clear_session")

    async def delete_session(self, session_id: str) -> dict:
        return self._call("delete_session", session_id)

    async def rename_session(self, session_id: str, title: str) -> dict:
        return self._call("rename_session", session_id, title)

    async def pin_session(self, session_id: str, pinned: bool) -> dict:
        return self._call("pin_session", session_id, pinned)

    async def move_session(self, session_id: str, game_key: str, game_label: str) -> dict:
        return self._call("move_session", session_id, game_key, game_label)

    async def save_chats(self, settings: dict) -> dict:
        return self._call("save_chats", settings)

    async def test_provider(self, provider_id: str) -> dict:
        return await self._acall("test_provider", provider_id)

    async def list_models(self, provider_id: str) -> dict:
        return await self._acall("list_models", provider_id)

    async def send_message(
        self,
        provider_id: str,
        model: str,
        content: str,
        request_id: str,
        about_game: str,
    ) -> dict:
        return self._call("start_chat", provider_id, model, content, request_id, about_game)

    async def cancel_chat(self, request_id: str) -> dict:
        return self._call("cancel_chat", request_id)

    async def set_game_context(self, snapshot: dict) -> dict:
        return self._call("set_game_context", snapshot)

    async def save_context(self, settings: dict) -> dict:
        return self._call("save_context", settings)

    async def save_web(self, settings: dict) -> dict:
        return self._call("save_web", settings)

    async def save_hearing(self, settings: dict) -> dict:
        return self._call("save_hearing", settings)

    async def push_to_talk(self) -> dict:
        return self._call("push_to_talk")

    async def stop_listening(self) -> dict:
        return self._call("stop_listening")

    async def set_hearing_activity(self, game_running: bool, sleeping: bool) -> dict:
        return self._call("set_hearing_activity", game_running, sleeping)

    async def save_voice(self, settings: dict) -> dict:
        return self._call("save_voice", settings)

    async def test_voice(self) -> dict:
        return await self._acall("test_voice")

    async def stop_speaking(self) -> dict:
        return self._call("stop_speaking")

    async def retry_kitten(self) -> dict:
        return await self._acall("retry_kitten")

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
            "look_at_screen",
            provider_id,
            model,
            question,
            request_id,
            game,
            image_b64,
            qam_hidden,
        )

    async def save_last_screenshot(self) -> dict:
        return self._call("save_last_screenshot")

    async def start_oauth(self, provider_id: str, flow: str) -> dict:
        return self._call("start_oauth", provider_id, flow)

    async def cancel_oauth(self, provider_id: str) -> dict:
        return self._call("cancel_oauth", provider_id)

    async def oauth_status(self, provider_id: str) -> dict:
        return self._call("oauth_status", provider_id)

    def _blocked(self) -> dict | None:
        if self._boot_error:
            return {"ok": False, "error": self._boot_error}
        if not hasattr(self, "service"):
            return {"ok": False, "error": "Deckling is still starting."}
        return None

    def _call(self, name: str, *args):  # type: ignore[no-untyped-def]
        blocked = self._blocked()
        if blocked:
            return blocked
        try:
            return getattr(self.service, name)(*args)
        except Exception as exc:  # noqa: BLE001 - returned to the UI, never logged raw
            decky.logger.warning("%s failed: %s", name, redact(str(exc)))
            return {"ok": False, "error": redact(str(exc))}

    async def _acall(self, name: str, *args):  # type: ignore[no-untyped-def]
        blocked = self._blocked()
        if blocked:
            return blocked
        try:
            return await getattr(self.service, name)(*args)
        except Exception as exc:  # noqa: BLE001 - returned to the UI, never logged raw
            decky.logger.warning("%s failed: %s", name, redact(str(exc)))
            return {"ok": False, "error": redact(str(exc))}


def _boot_paths() -> list[str]:
    paths = [diagnostics_path()]
    log_dir = os.environ.get("DECKY_PLUGIN_LOG_DIR")
    if log_dir:
        paths.append(os.path.join(log_dir, "boot-error.txt"))
    return paths


def _install_log_ring() -> None:
    if getattr(decky.logger, "_deckling_ring", False):
        return

    class _Ring(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            try:
                remember(redact(self.format(record)))
            except Exception:
                return

    handler = _Ring()
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    decky.logger.addHandler(handler)
    decky.logger._deckling_ring = True  # type: ignore[attr-defined]


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
