"""Plugin behaviour shared by main.py. Network work runs off the Decky event loop."""

from __future__ import annotations

import asyncio
import logging
import secrets
import threading
import time
from typing import Any, Protocol

from . import claude_code, oauth, providers
from .catalog import catalog_payload, get_kind
from .claude_code import ClaudeCodeError
from .http_util import HttpError
from .oauth import OAuthError
from .redact import redact
from .store import Store, public_provider, public_session_summary

EVENT = "ai_assistant_event"
_GAME_NAME_LIMIT = 120


class Host(Protocol):
    async def emit(self, event: str, payload: dict[str, Any]) -> None: ...

    def info(self, message: str, *args: object) -> None: ...

    def warning(self, message: str, *args: object) -> None: ...


class _NullHost:
    async def emit(self, event: str, payload: dict[str, Any]) -> None:
        return None

    def info(self, message: str, *args: object) -> None:
        logging.getLogger("ai_assistant").info(message, *args)

    def warning(self, message: str, *args: object) -> None:
        logging.getLogger("ai_assistant").warning(message, *args)


def _fail(message: str) -> dict[str, Any]:
    return {"ok": False, "error": redact(message)}


def _about_game(name: str) -> str:
    cleaned = " ".join(str(name or "").split())
    return cleaned[:_GAME_NAME_LIMIT]


class AssistantService:
    def __init__(self, settings_dir: str, runtime_dir: str, host: Host | None = None) -> None:
        self.store = Store(settings_dir, runtime_dir)
        self.host = host or _NullHost()
        self._streams: dict[str, threading.Event] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._oauth: dict[str, dict[str, Any]] = {}
        self._oauth_cancel: dict[str, threading.Event] = {}

    def state(self) -> dict[str, Any]:
        config = self.store.load_config()
        sessions, current = self.store.ensure_session()
        return {
            "ok": True,
            "catalog": catalog_payload(),
            "providers": [public_provider(item) for item in config["providers"]],
            "default_provider_id": config.get("default_provider_id") or "",
            "default_model": config.get("default_model") or "",
            "system_prompt": config.get("system_prompt") or "",
            "current_session_id": current["id"],
            "sessions": [public_session_summary(item) for item in sessions["sessions"]],
            "messages": list(current.get("messages") or []),
        }

    def save_provider(self, incoming: dict[str, Any]) -> dict[str, Any]:
        record = self.store.upsert_provider(incoming)
        self.host.info("Saved provider kind=%s", record.get("kind"))
        return {"ok": True, "provider": public_provider(record), **self._state_bits()}

    def delete_provider(self, provider_id: str) -> dict[str, Any]:
        self.store.delete_provider(provider_id)
        self.host.info("Deleted provider")
        return {"ok": True, **self._state_bits()}

    def save_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(settings, dict):
            raise ValueError("Settings must be an object")
        self.store.update_settings(
            str(settings.get("system_prompt") or ""),
            str(settings.get("default_provider_id") or ""),
            str(settings.get("default_model") or ""),
        )
        return {"ok": True, **self._state_bits()}

    def new_session(self) -> dict[str, Any]:
        current = self.store.new_session()
        return {"ok": True, "current_session_id": current["id"], "messages": [], **self._session_bits()}

    def switch_session(self, session_id: str) -> dict[str, Any]:
        current = self.store.switch_session(session_id)
        return {
            "ok": True,
            "current_session_id": current["id"],
            "messages": list(current.get("messages") or []),
            **self._session_bits(),
        }

    def clear_session(self) -> dict[str, Any]:
        current = self.store.clear_session()
        return {"ok": True, "current_session_id": current["id"], "messages": [], **self._session_bits()}

    def delete_session(self, session_id: str) -> dict[str, Any]:
        self.store.delete_session(session_id)
        _, current = self.store.ensure_session()
        return {
            "ok": True,
            "current_session_id": current["id"],
            "messages": list(current.get("messages") or []),
            **self._session_bits(),
        }

    async def test_provider(self, provider_id: str) -> dict[str, Any]:
        provider = await self._provider_ready(provider_id)
        try:
            models = await asyncio.to_thread(providers.list_models, provider)
        except (HttpError, ValueError, OSError, ClaudeCodeError) as exc:
            self.host.warning("Connection test failed kind=%s", provider.get("kind"))
            return _fail(str(exc))
        self.host.info("Connection test ok kind=%s models=%s", provider.get("kind"), len(models))
        preview = models[:50]
        if preview:
            message = f"Connected. {len(models)} model{'s' if len(models) != 1 else ''} available."
        else:
            message = "Connected, but the server did not list any models. You can still type a model id."
        return {"ok": True, "message": message, "models": preview}

    async def list_models(self, provider_id: str) -> dict[str, Any]:
        provider = await self._provider_ready(provider_id)
        try:
            models = await asyncio.to_thread(providers.list_models, provider)
        except (HttpError, ValueError, OSError, ClaudeCodeError) as exc:
            return _fail(str(exc))
        return {"ok": True, "models": models[:80]}

    def start_chat(
        self,
        provider_id: str,
        model: str,
        content: str,
        request_id: str,
        about_game: str,
    ) -> dict[str, Any]:
        if not request_id or len(request_id) > 80:
            raise ValueError("Missing request id")
        if self._streams:
            return _fail("A response is still streaming")
        text = str(content or "").strip()
        game = _about_game(about_game)
        if game and text:
            text = f"[Playing: {game}]\n\n{text}"
        elif game and not text:
            text = f"I'm playing {game} on my Steam Deck. Give me a short, spoiler-free tip."
        if not text:
            return _fail("Type a message first")
        _, current = self.store.ensure_session()
        self.store.append_message(current["id"], "user", text)
        cancel = threading.Event()
        self._streams[request_id] = cancel
        task = asyncio.get_running_loop().create_task(
            self._run_chat(provider_id, model, request_id, current["id"], cancel)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        refreshed, current = self.store.ensure_session()
        return {
            "ok": True,
            "request_id": request_id,
            "messages": list(current.get("messages") or []),
            "sessions": [public_session_summary(item) for item in refreshed["sessions"]],
        }

    def cancel_chat(self, request_id: str) -> dict[str, Any]:
        cancel = self._streams.get(request_id)
        if cancel is None:
            return {"ok": True, "message": "Nothing to stop"}
        cancel.set()
        return {"ok": True}

    def start_oauth(self, provider_id: str, flow: str) -> dict[str, Any]:
        provider = self.store.get_provider(provider_id)
        kind = get_kind(str(provider.get("kind")))
        if kind.kind == "claude_code":
            if str(provider.get("base_url") or "").strip():
                return _fail(
                    "Remote mode uses the Claude Code login on the PC running the bridge. "
                    "On that PC run claude login or claude setup-token."
                )
            flow = "setup-token"
        elif kind.oauth == "xai":
            if flow not in {"device"}:
                return _fail("xAI sign-in uses the device-code flow.")
        elif kind.oauth == "none":
            return _fail(f"{kind.label} does not offer third-party OAuth. Use an API key.")
        elif flow not in {"device", "pkce"}:
            return _fail("Choose device or PKCE sign-in")
        previous = self._oauth_cancel.get(provider_id)
        if previous is not None:
            previous.set()
        cancel = threading.Event()
        self._oauth_cancel[provider_id] = cancel
        self._oauth[provider_id] = {"status": "starting", "flow": flow, "message": "Contacting the provider…"}
        task = asyncio.get_running_loop().create_task(self._run_oauth(provider_id, flow, cancel))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return {"ok": True, "status": "starting", "flow": flow, "message": "Contacting the provider…"}

    def cancel_oauth(self, provider_id: str) -> dict[str, Any]:
        cancel = self._oauth_cancel.get(provider_id)
        if cancel is not None:
            cancel.set()
        current = self._oauth.get(provider_id) or {}
        current["status"] = "idle"
        current["message"] = "Login cancelled"
        self._oauth[provider_id] = current
        return {"ok": True, **self._public_oauth(provider_id)}

    def oauth_status(self, provider_id: str) -> dict[str, Any]:
        return {"ok": True, **self._public_oauth(provider_id)}

    async def shutdown(self) -> None:
        for cancel in list(self._streams.values()):
            cancel.set()
        for cancel in list(self._oauth_cancel.values()):
            cancel.set()
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    def _state_bits(self) -> dict[str, Any]:
        config = self.store.load_config()
        return {
            "providers": [public_provider(item) for item in config["providers"]],
            "default_provider_id": config.get("default_provider_id") or "",
            "default_model": config.get("default_model") or "",
            "system_prompt": config.get("system_prompt") or "",
        }

    def _session_bits(self) -> dict[str, Any]:
        data = self.store.load_sessions()
        return {"sessions": [public_session_summary(item) for item in data["sessions"]]}

    def _public_oauth(self, provider_id: str) -> dict[str, Any]:
        raw = dict(self._oauth.get(provider_id) or {"status": "idle", "message": ""})
        # device_code and verifiers never leave the process.
        for secret_key in ("device_auth_id", "device_code", "code_verifier", "state", "port"):
            raw.pop(secret_key, None)
        return raw

    async def _provider_ready(self, provider_id: str) -> dict[str, Any]:
        provider = self.store.get_provider(provider_id)
        refreshed = await asyncio.to_thread(self._refresh_if_needed, provider)
        if refreshed is not None:
            provider = self.store.get_provider(provider_id)
        return provider

    def _refresh_if_needed(self, provider: dict[str, Any]) -> dict[str, Any] | None:
        try:
            fields = oauth.refresh_access_token(provider)
        except OAuthError as exc:
            self.host.warning("Token refresh failed kind=%s", provider.get("kind"))
            raise ValueError(str(exc)) from exc
        if not fields:
            return None
        self.store.set_oauth_tokens(
            str(provider["id"]),
            access_token=fields["access_token"],
            refresh_token=fields.get("refresh_token") or "",
            expires_at=int(fields["expires_at"]),
        )
        self.host.info("Refreshed OAuth token kind=%s", provider.get("kind"))
        return fields

    async def _emit(self, payload: dict[str, Any]) -> None:
        await self.host.emit(EVENT, payload)

    async def _run_chat(
        self,
        provider_id: str,
        model: str,
        request_id: str,
        session_id: str,
        cancel: threading.Event,
    ) -> None:
        collected: list[str] = []
        meta: dict[str, Any] = {}
        try:
            provider = await self._provider_ready(provider_id)
            chosen = model.strip() or str(provider.get("default_model") or "")
            config = self.store.load_config()
            _data, current = self.store.ensure_session()
            if current["id"] != session_id:
                current = next(item for item in _data["sessions"] if item.get("id") == session_id)
            history = [
                {"role": item["role"], "content": item["content"]}
                for item in (current.get("messages") or [])
                if item.get("role") in {"user", "assistant"}
            ]
            messages = providers.prepare_messages(provider, history, str(config.get("system_prompt") or ""))
            meta["session_id"] = str(current.get("claude_session_id") or "")
            self.host.info("Chat started kind=%s model=%s", provider.get("kind"), chosen)

            def _produce(queue: asyncio.Queue[tuple[str, object]], loop: asyncio.AbstractEventLoop) -> None:
                try:
                    for delta in providers.iter_text(provider, messages, chosen, cancel, meta):
                        if cancel.is_set():
                            break
                        asyncio.run_coroutine_threadsafe(queue.put(("delta", delta)), loop).result()
                except Exception as exc:  # noqa: BLE001 - surfaced to the UI as redacted text
                    asyncio.run_coroutine_threadsafe(queue.put(("error", exc)), loop).result()
                finally:
                    asyncio.run_coroutine_threadsafe(queue.put(("end", None)), loop).result()

            loop = asyncio.get_running_loop()
            queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
            worker = asyncio.create_task(asyncio.to_thread(_produce, queue, loop))
            try:
                while True:
                    kind, payload = await queue.get()
                    if kind == "end":
                        break
                    if kind == "error":
                        raise payload if isinstance(payload, Exception) else RuntimeError(str(payload))
                    text = str(payload)
                    collected.append(text)
                    await self._emit({"type": "chat_delta", "request_id": request_id, "text": text})
            finally:
                if not worker.done():
                    await worker
            if cancel.is_set() and not collected:
                await self._emit({"type": "chat_done", "request_id": request_id, "text": "", "cancelled": True})
                return
            full = "".join(collected)
            if full:
                self.store.append_message(session_id, "assistant", full)
            resumed_now = str(meta.get("claude_session_id") or "")
            if resumed_now:
                self.store.set_claude_session(session_id, resumed_now)
            self.host.info("Chat finished kind=%s chars=%s", provider.get("kind"), len(full))
            data = self.store.load_sessions()
            shown = next((item for item in data["sessions"] if item.get("id") == session_id), None)
            await self._emit(
                {
                    "type": "chat_done",
                    "request_id": request_id,
                    "session_id": session_id,
                    "text": full,
                    "cancelled": cancel.is_set(),
                    "messages": list((shown or {}).get("messages") or []),
                    "sessions": [public_session_summary(item) for item in data["sessions"]],
                }
            )
        except asyncio.CancelledError:
            cancel.set()
            raise
        except Exception as exc:
            self.host.warning("Chat failed: %s", redact(str(exc)))
            await self._emit(
                {"type": "chat_error", "request_id": request_id, "session_id": session_id, "error": redact(str(exc))}
            )
        finally:
            resumed = str(meta.get("claude_session_id") or "")
            if resumed:
                try:
                    self.store.set_claude_session(session_id, resumed)
                except Exception:
                    self.host.warning("Could not store the Claude Code session id")
            self._streams.pop(request_id, None)

    async def _run_oauth(self, provider_id: str, flow: str, cancel: threading.Event) -> None:
        try:
            provider = self.store.get_provider(provider_id)
            kind = str(provider.get("kind"))
            if flow == "setup-token":
                await self._run_claude_setup(provider_id, cancel)
                return
            if flow == "device":
                started = await asyncio.to_thread(self._device_start, provider)
            else:
                started = self._pkce_start(provider)
            self._oauth[provider_id] = {**started, "status": "pending", "flow": flow}
            await self._emit({"type": "oauth", "provider_id": provider_id, **self._public_oauth(provider_id)})
            if flow == "device":
                tokens = await asyncio.to_thread(self._device_wait, provider, started, cancel)
            else:
                tokens = await asyncio.to_thread(self._pkce_wait, provider, started, cancel)
            self.store.set_oauth_tokens(
                provider_id,
                access_token=tokens["access_token"],
                refresh_token=tokens.get("refresh_token") or "",
                expires_at=int(tokens["expires_at"]),
            )
            self._oauth[provider_id] = {
                "status": "success",
                "flow": flow,
                "message": "Signed in. You can test the connection.",
            }
            self.host.info("OAuth finished kind=%s flow=%s", kind, flow)
        except asyncio.CancelledError:
            cancel.set()
            raise
        except Exception as exc:
            if cancel.is_set() and "cancelled" in str(exc).lower():
                self._oauth[provider_id] = {"status": "idle", "flow": flow, "message": "Login cancelled"}
            else:
                self.host.warning("OAuth failed kind flow=%s", flow)
                self._oauth[provider_id] = {"status": "error", "flow": flow, "message": redact(str(exc))}
        finally:
            self._oauth_cancel.pop(provider_id, None)
            await self._emit({"type": "oauth", "provider_id": provider_id, **self._public_oauth(provider_id)})

    async def _run_claude_setup(self, provider_id: str, cancel: threading.Event) -> None:
        binary = claude_code.find_claude()
        if not binary:
            raise ClaudeCodeError(claude_code.INSTALL_HINT)
        loop = asyncio.get_running_loop()
        self._oauth[provider_id] = {
            "status": "pending",
            "flow": "setup-token",
            "message": "Starting claude setup-token…",
        }
        await self._emit({"type": "oauth", "provider_id": provider_id, **self._public_oauth(provider_id)})

        def on_update(info: dict[str, str]) -> None:
            self._oauth[provider_id] = {
                "status": "pending",
                "flow": "setup-token",
                "verification_url": info.get("verification_url") or "",
                "user_code": info.get("user_code") or "",
                "message": info.get("message") or "",
            }
            future = asyncio.run_coroutine_threadsafe(
                self._emit({"type": "oauth", "provider_id": provider_id, **self._public_oauth(provider_id)}),
                loop,
            )
            future.result()

        token = await asyncio.to_thread(claude_code.run_setup_token, binary, cancel, on_update)
        self.store.set_api_key(provider_id, token)
        self._oauth[provider_id] = {
            "status": "success",
            "flow": "setup-token",
            "message": "Signed in. The Claude Code token is saved on this Deck.",
        }
        self.host.info("Claude Code setup-token saved")

    def _device_start(self, provider: dict[str, Any]) -> dict[str, Any]:
        client_id = str(provider.get("oauth_client_id") or "")
        if provider.get("kind") == "openai":
            started = oauth.openai_device_start(client_id)
            return {
                **started,
                "message": "Open the verification page and enter the code.",
            }
        if provider.get("kind") == "gemini":
            started = oauth.google_device_start(client_id)
            return {**started, "message": "Open the verification page and enter the code."}
        if provider.get("kind") == "xai":
            return oauth.xai_device_start()
        raise OAuthError("This provider does not offer device login")

    def _device_wait(self, provider: dict[str, Any], started: dict[str, Any], cancel: threading.Event) -> dict[str, Any]:
        interval = int(started.get("interval") or 5)
        expires_in = int(started.get("expires_in") or 15 * 60)
        deadline = time.time() + max(30, min(expires_in, 15 * 60))
        client_id = str(provider.get("oauth_client_id") or "")
        secret = str(provider.get("oauth_client_secret") or "")
        while not cancel.is_set() and time.time() < deadline:
            try:
                if provider.get("kind") == "openai":
                    tokens = oauth.openai_device_poll(client_id, str(started["device_auth_id"]), str(started["user_code"]))
                elif provider.get("kind") == "xai":
                    tokens = oauth.xai_device_poll(str(started["device_code"]))
                else:
                    tokens = oauth.google_device_poll(client_id, secret, str(started["device_code"]))
            except OAuthError as exc:
                if str(exc) == "slow_down":
                    interval += 5
                    tokens = None
                else:
                    raise
            if tokens:
                return tokens
            if cancel.wait(interval):
                break
        if cancel.is_set():
            raise OAuthError("Login cancelled")
        raise OAuthError("Login timed out. Start it again when you are ready to approve it.")

    def _pkce_start(self, provider: dict[str, Any]) -> dict[str, Any]:
        client_id = str(provider.get("oauth_client_id") or "")
        if not client_id:
            raise OAuthError("Paste an OAuth client ID first. API-key access does not need one.")
        verifier, challenge = oauth.pkce_pair()
        state = secrets.token_urlsafe(24)
        if provider.get("kind") == "openai":
            port = oauth.PKCE_PORT_OPENAI
            redirect = f"http://127.0.0.1:{port}/auth/callback"
            url = oauth.openai_authorize_url(client_id, redirect, challenge, state)
        elif provider.get("kind") == "gemini":
            port = oauth.PKCE_PORT_GOOGLE
            redirect = f"http://127.0.0.1:{port}/"
            url = oauth.google_authorize_url(client_id, redirect, challenge, state)
        else:
            raise OAuthError("This provider does not offer PKCE login")
        return {
            "verification_url": url,
            "user_code": "",
            "message": f"Register redirect URI {redirect} on this OAuth client if you have not already, then open the page.",
            "redirect_uri": redirect,
            "port": port,
            "code_verifier": verifier,
            "state": state,
        }

    def _pkce_wait(self, provider: dict[str, Any], started: dict[str, Any], cancel: threading.Event) -> dict[str, Any]:
        code = oauth.wait_for_redirect(int(started["port"]), str(started["state"]), cancel)
        client_id = str(provider.get("oauth_client_id") or "")
        if provider.get("kind") == "openai":
            return oauth.exchange_openai_code(
                client_id=client_id,
                code=code,
                code_verifier=str(started["code_verifier"]),
                redirect_uri=str(started["redirect_uri"]),
            )
        return oauth.exchange_google_code(
            client_id,
            str(provider.get("oauth_client_secret") or ""),
            code,
            str(started["code_verifier"]),
            str(started["redirect_uri"]),
        )


