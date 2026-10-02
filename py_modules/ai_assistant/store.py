"""Credential and session storage. Secret files are created mode 0600."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import uuid
from typing import Any

from .catalog import get_kind

_MAX_SESSIONS = 30
_MAX_MESSAGES = 200
_MAX_CONTENT = 100_000


def _chmod_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)
    os.chmod(path, 0o700)


def _atomic_write(path: str, payload: dict[str, Any]) -> None:
    directory = os.path.dirname(path)
    _chmod_dir(directory)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_json(path: str, default: dict[str, Any]) -> dict[str, Any]:
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return default
    return data


def _blank_config() -> dict[str, Any]:
    return {
        "version": 1,
        "system_prompt": "",
        "default_provider_id": "",
        "default_model": "",
        "providers": [],
    }


def _blank_sessions() -> dict[str, Any]:
    return {"version": 1, "current_id": "", "sessions": []}


def _merge_secret(incoming: Any, previous: str) -> str:
    """``None`` keeps the stored secret. ``\"\"`` clears it. Any other string replaces it."""
    if incoming is None:
        return previous
    if not isinstance(incoming, str):
        raise ValueError("Secret fields must be strings")
    return incoming.strip()


class Store:
    def __init__(self, settings_dir: str, runtime_dir: str) -> None:
        self.settings_dir = settings_dir
        self.runtime_dir = runtime_dir
        self.credentials_path = os.path.join(settings_dir, "credentials.json")
        self.sessions_path = os.path.join(runtime_dir, "sessions.json")
        self._lock = threading.RLock()
        _chmod_dir(settings_dir)
        _chmod_dir(runtime_dir)

    def load_config(self) -> dict[str, Any]:
        with self._lock:
            data = _read_json(self.credentials_path, _blank_config())
            data.setdefault("providers", [])
            data.setdefault("system_prompt", "")
            data.setdefault("default_provider_id", "")
            data.setdefault("default_model", "")
            return data

    def save_config(self, data: dict[str, Any]) -> None:
        with self._lock:
            _atomic_write(self.credentials_path, data)

    def load_sessions(self) -> dict[str, Any]:
        with self._lock:
            data = _read_json(self.sessions_path, _blank_sessions())
            data.setdefault("sessions", [])
            data.setdefault("current_id", "")
            return data

    def save_sessions(self, data: dict[str, Any]) -> None:
        with self._lock:
            sessions = data.get("sessions") or []
            data["sessions"] = sessions[:_MAX_SESSIONS]
            _atomic_write(self.sessions_path, data)

    def delete_private_files(self) -> None:
        with self._lock:
            for path in (self.credentials_path, self.sessions_path):
                try:
                    os.remove(path)
                except FileNotFoundError:
                    pass

    def upsert_provider(self, incoming: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(incoming, dict):
            raise ValueError("Provider must be an object")
        kind = get_kind(str(incoming.get("kind") or ""))
        name = str(incoming.get("name") or "").strip()
        if not name or len(name) > 80:
            raise ValueError("Provider name must be 1-80 characters")
        base_url = str(incoming.get("base_url") or kind.default_base_url).strip()
        if kind.kind == "custom" and not base_url:
            raise ValueError("Custom providers need a base URL")
        if base_url:
            from .http_util import check_url

            check_url(base_url if "://" in base_url else f"http://{base_url}")
        model = str(incoming.get("default_model") or kind.default_model).strip()
        if len(model) > 200:
            raise ValueError("Model id is too long")
        try:
            max_tokens = int(incoming.get("max_tokens") or 1024)
        except (TypeError, ValueError) as exc:
            raise ValueError("Max tokens must be a number") from exc
        max_tokens = max(1, min(max_tokens, 8192))

        with self._lock:
            config = self.load_config()
            providers: list[dict[str, Any]] = list(config["providers"])
            provider_id = str(incoming.get("id") or "")
            existing = next((item for item in providers if item.get("id") == provider_id), None)
            if provider_id and existing is None:
                raise ValueError("That provider no longer exists")
            record = dict(existing or {})
            record.update(
                {
                    "id": existing.get("id") if existing else uuid.uuid4().hex,
                    "kind": kind.kind,
                    "name": name,
                    "base_url": base_url,
                    "default_model": model,
                    "max_tokens": max_tokens,
                    "api_key": _merge_secret(incoming.get("api_key"), str(record.get("api_key") or "")),
                    "oauth_client_id": str(
                        incoming.get("oauth_client_id")
                        if incoming.get("oauth_client_id") is not None
                        else record.get("oauth_client_id") or ""
                    ).strip(),
                    "oauth_client_secret": _merge_secret(
                        incoming.get("oauth_client_secret"),
                        str(record.get("oauth_client_secret") or ""),
                    ),
                    "oauth_access_token": str(record.get("oauth_access_token") or ""),
                    "oauth_refresh_token": str(record.get("oauth_refresh_token") or ""),
                    "oauth_expires_at": int(record.get("oauth_expires_at") or 0),
                }
            )
            if existing:
                providers = [record if item.get("id") == record["id"] else item for item in providers]
            else:
                providers.append(record)
            config["providers"] = providers
            if not config.get("default_provider_id"):
                config["default_provider_id"] = record["id"]
                config["default_model"] = record["default_model"]
            self.save_config(config)
            return record

    def delete_provider(self, provider_id: str) -> None:
        with self._lock:
            config = self.load_config()
            config["providers"] = [item for item in config["providers"] if item.get("id") != provider_id]
            if config.get("default_provider_id") == provider_id:
                config["default_provider_id"] = ""
                config["default_model"] = ""
                if config["providers"]:
                    first = config["providers"][0]
                    config["default_provider_id"] = first["id"]
                    config["default_model"] = first.get("default_model") or ""
            self.save_config(config)

    def update_settings(self, system_prompt: str, default_provider_id: str, default_model: str) -> dict[str, Any]:
        if len(system_prompt) > 8000:
            raise ValueError("System prompt is too long")
        if len(default_model) > 200:
            raise ValueError("Model id is too long")
        with self._lock:
            config = self.load_config()
            if default_provider_id and not any(item.get("id") == default_provider_id for item in config["providers"]):
                raise ValueError("Choose a saved provider")
            config["system_prompt"] = system_prompt
            config["default_provider_id"] = default_provider_id
            config["default_model"] = default_model.strip()
            self.save_config(config)
            return config

    def set_oauth_tokens(
        self,
        provider_id: str,
        *,
        access_token: str,
        refresh_token: str,
        expires_at: int,
    ) -> None:
        with self._lock:
            config = self.load_config()
            found = False
            for item in config["providers"]:
                if item.get("id") == provider_id:
                    item["oauth_access_token"] = access_token
                    if refresh_token:
                        item["oauth_refresh_token"] = refresh_token
                    item["oauth_expires_at"] = expires_at
                    found = True
            if not found:
                raise ValueError("That provider no longer exists")
            self.save_config(config)

    def get_provider(self, provider_id: str) -> dict[str, Any]:
        config = self.load_config()
        for item in config["providers"]:
            if item.get("id") == provider_id:
                return item
        raise ValueError("That provider no longer exists")

    def ensure_session(self) -> tuple[dict[str, Any], dict[str, Any]]:
        data = self.load_sessions()
        sessions: list[dict[str, Any]] = data["sessions"]
        current = next((item for item in sessions if item.get("id") == data.get("current_id")), None)
        if current is None:
            current = _new_session()
            sessions.insert(0, current)
            data["current_id"] = current["id"]
            data["sessions"] = sessions[:_MAX_SESSIONS]
            self.save_sessions(data)
        return data, current

    def new_session(self) -> dict[str, Any]:
        with self._lock:
            data = self.load_sessions()
            current = _new_session()
            data["sessions"] = [current, *data["sessions"]][:_MAX_SESSIONS]
            data["current_id"] = current["id"]
            self.save_sessions(data)
            return current

    def switch_session(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            data = self.load_sessions()
            match = next((item for item in data["sessions"] if item.get("id") == session_id), None)
            if match is None:
                raise ValueError("That conversation no longer exists")
            data["current_id"] = session_id
            self.save_sessions(data)
            return match

    def clear_session(self, session_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            data, current = self.ensure_session()
            target_id = session_id or current["id"]
            for item in data["sessions"]:
                if item.get("id") == target_id:
                    item["messages"] = []
                    item["title"] = "New chat"
                    item["updated_at"] = int(time.time())
                    self.save_sessions(data)
                    return item
            raise ValueError("That conversation no longer exists")

    def delete_session(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            data = self.load_sessions()
            data["sessions"] = [item for item in data["sessions"] if item.get("id") != session_id]
            if data.get("current_id") == session_id:
                if data["sessions"]:
                    data["current_id"] = data["sessions"][0]["id"]
                else:
                    created = _new_session()
                    data["sessions"] = [created]
                    data["current_id"] = created["id"]
            self.save_sessions(data)
            return data

    def append_message(self, session_id: str, role: str, content: str) -> dict[str, Any]:
        text = content[:_MAX_CONTENT]
        with self._lock:
            data = self.load_sessions()
            match = next((item for item in data["sessions"] if item.get("id") == session_id), None)
            if match is None:
                raise ValueError("That conversation no longer exists")
            message = {
                "id": uuid.uuid4().hex,
                "role": role,
                "content": text,
                "created_at": int(time.time()),
            }
            messages = list(match.get("messages") or [])
            messages.append(message)
            match["messages"] = messages[-_MAX_MESSAGES:]
            match["updated_at"] = message["created_at"]
            if role == "user" and (not match.get("title") or match.get("title") == "New chat"):
                title = " ".join(text.split())
                match["title"] = (title[:48] + "…") if len(title) > 48 else title or "New chat"
            self.save_sessions(data)
            return message


def _new_session() -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "title": "New chat",
        "updated_at": int(time.time()),
        "messages": [],
    }


def public_provider(record: dict[str, Any]) -> dict[str, Any]:
    """Provider fields that are safe to send to the frontend."""
    api_key = str(record.get("api_key") or "")
    from .redact import last4

    return {
        "id": record.get("id") or "",
        "kind": record.get("kind") or "",
        "name": record.get("name") or "",
        "base_url": record.get("base_url") or "",
        "default_model": record.get("default_model") or "",
        "max_tokens": int(record.get("max_tokens") or 1024),
        "has_api_key": bool(api_key),
        "api_key_last4": last4(api_key),
        "oauth_client_id": record.get("oauth_client_id") or "",
        "has_oauth_secret": bool(record.get("oauth_client_secret")),
        "oauth_connected": bool(record.get("oauth_access_token") or record.get("oauth_refresh_token")),
        "oauth_expires_at": int(record.get("oauth_expires_at") or 0),
    }


def public_session_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record.get("id") or "",
        "title": record.get("title") or "New chat",
        "updated_at": int(record.get("updated_at") or 0),
    }
