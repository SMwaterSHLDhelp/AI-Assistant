"""Chat backends. Each kind implements listing models and streaming text deltas."""

from __future__ import annotations

import json
import threading
import urllib.parse
from collections.abc import Iterator
from typing import Any

from .http_util import HttpError, iter_lines, join_url, request_json
from .redact import redact
from .sse import iter_json_lines, iter_sse_json

ANTHROPIC_VERSION = "2023-06-01"
_CONTEXT_MESSAGES = 40


def bearer_token(provider: dict[str, Any]) -> str:
    return str(provider.get("oauth_access_token") or provider.get("api_key") or "")


def require_credentials(provider: dict[str, Any]) -> str:
    token = bearer_token(provider)
    kind = provider.get("kind")
    if kind in {"openai", "anthropic", "gemini", "hermes"} and not token:
        raise ValueError("Add an API key, or finish OAuth sign-in, before chatting")
    return token


def prepare_messages(provider: dict[str, Any], history: list[dict[str, str]], system_prompt: str) -> list[dict[str, str]]:
    messages = [{"role": item["role"], "content": item["content"]} for item in history[-_CONTEXT_MESSAGES:]]
    prompt = (system_prompt or "").strip()
    if prompt:
        messages.insert(0, {"role": "system", "content": prompt})
    if provider.get("kind") == "gemini":
        return messages
    return messages


def list_models(provider: dict[str, Any]) -> list[str]:
    kind = str(provider.get("kind") or "")
    dispatch = {
        "openai": _list_openai_models,
        "hermes": _list_openai_models,
        "llamacpp": _list_openai_models,
        "custom": _list_openai_models,
        "anthropic": _list_anthropic_models,
        "gemini": _list_gemini_models,
        "ollama": _list_ollama_models,
    }
    handler = dispatch.get(kind)
    if handler is None:
        raise ValueError(f"Unknown provider type: {kind}")
    models = handler(provider)
    if kind == "hermes":
        hermes = [item for item in models if "hermes" in item.lower()]
        if hermes:
            return hermes
    if kind == "openai":
        chat = [item for item in models if _looks_like_chat_model(item)]
        if chat:
            return chat
    return models


def iter_text(provider: dict[str, Any], messages: list[dict[str, str]], model: str, cancel: threading.Event) -> Iterator[str]:
    if not model.strip():
        raise ValueError("Choose a model")
    kind = str(provider.get("kind") or "")
    dispatch = {
        "openai": _iter_openai,
        "hermes": _iter_openai,
        "llamacpp": _iter_openai,
        "custom": _iter_openai,
        "anthropic": _iter_anthropic,
        "gemini": _iter_gemini,
        "ollama": _iter_ollama,
    }
    handler = dispatch.get(kind)
    if handler is None:
        raise ValueError(f"Unknown provider type: {kind}")
    yield from handler(provider, messages, model.strip(), cancel)


def _auth_headers(provider: dict[str, Any]) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = bearer_token(provider)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    host = urllib.parse.urlsplit(str(provider.get("base_url") or "")).hostname or ""
    if host == "openrouter.ai" or host.endswith(".openrouter.ai"):
        headers["HTTP-Referer"] = "https://github.com/SMwaterSHLDhelp/AI-Assistant"
        headers["X-Title"] = "AI Assistant"
    return headers


def _base(provider: dict[str, Any]) -> str:
    base = str(provider.get("base_url") or "").strip()
    if not base:
        raise ValueError("This provider needs a base URL")
    return base.rstrip("/")


def _max_tokens(provider: dict[str, Any]) -> int:
    try:
        value = int(provider.get("max_tokens") or 1024)
    except (TypeError, ValueError):
        value = 1024
    return max(1, min(value, 8192))


def _looks_like_chat_model(model_id: str) -> bool:
    lower = model_id.lower()
    blocked = ("embedding", "whisper", "tts", "dall-e", "davinci", "babbage", "moderation", "transcribe", "audio")
    if any(word in lower for word in blocked):
        return False
    return lower.startswith(("gpt-", "chatgpt-", "o1", "o3", "o4", "ft:"))


def _ids_from_openai_payload(payload: Any) -> list[str]:
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    found: list[str] = []
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            found.append(row["id"])
    return sorted(set(found))


def _list_openai_models(provider: dict[str, Any]) -> list[str]:
    if provider.get("kind") in {"openai", "hermes"}:
        require_credentials(provider)
    payload = request_json("GET", join_url(_base(provider), "models"), headers=_auth_headers(provider), timeout=20)
    return _ids_from_openai_payload(payload)


def _list_anthropic_models(provider: dict[str, Any]) -> list[str]:
    token = require_credentials(provider)
    headers = {
        "x-api-key": token,
        "anthropic-version": ANTHROPIC_VERSION,
    }
    payload = request_json("GET", join_url(_base(provider), "v1/models"), headers=headers, timeout=20)
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    found = [row["id"] for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str)]
    return sorted(set(found))


def _list_gemini_models(provider: dict[str, Any]) -> list[str]:
    headers = _gemini_headers(provider)
    payload = request_json("GET", join_url(_base(provider), "models"), headers=headers, timeout=20)
    rows = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    found: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        methods = row.get("supportedGenerationMethods") or []
        if methods and "generateContent" not in methods:
            continue
        name = str(row.get("name") or "")
        if name.startswith("models/"):
            name = name[len("models/") :]
        if name:
            found.append(name)
    return sorted(set(found))


def _list_ollama_models(provider: dict[str, Any]) -> list[str]:
    headers = _auth_headers(provider)
    payload = request_json("GET", join_url(_base(provider), "api/tags"), headers=headers, timeout=15)
    rows = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    found: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name") or row.get("model")
        if isinstance(name, str) and name:
            found.append(name)
    return sorted(set(found))


def _gemini_headers(provider: dict[str, Any]) -> dict[str, str]:
    token = require_credentials(provider)
    headers = {"Content-Type": "application/json"}
    # API keys are not bearer tokens. OAuth access tokens are.
    if token.startswith("ya29.") or provider.get("oauth_access_token"):
        headers["Authorization"] = f"Bearer {token}"
    else:
        headers["x-goog-api-key"] = token
    return headers


def _split_system(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
    system: list[str] = []
    rest: list[dict[str, str]] = []
    for message in messages:
        if message["role"] == "system":
            system.append(message["content"])
        else:
            role = "assistant" if message["role"] == "assistant" else "user"
            rest.append({"role": role, "content": message["content"]})
    return "\n\n".join(part for part in system if part.strip()), rest


def _merge_roles(messages: list[dict[str, str]], assistant_role: str) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    for message in messages:
        role = assistant_role if message["role"] == "assistant" else "user"
        if merged and merged[-1]["role"] == role:
            merged[-1]["content"] += "\n\n" + message["content"]
        else:
            merged.append({"role": role, "content": message["content"]})
    if merged and merged[0]["role"] != "user":
        merged.insert(0, {"role": "user", "content": "(conversation continues)"})
    return merged


def _openai_delta(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    error = payload.get("error")
    if isinstance(error, dict):
        raise HttpError(400, redact(str(error.get("message") or error))[:400])
    if isinstance(error, str):
        raise HttpError(400, redact(error)[:400])
    choices = payload.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return ""
    delta = choices[0].get("delta") or {}
    if isinstance(delta, dict) and isinstance(delta.get("content"), str):
        return delta["content"]
    message = choices[0].get("message") or {}
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]
    return ""


def _iter_openai(provider: dict[str, Any], messages: list[dict[str, str]], model: str, cancel: threading.Event) -> Iterator[str]:
    if provider.get("kind") in {"openai", "hermes"}:
        require_credentials(provider)
    token_field = "max_completion_tokens" if provider.get("kind") == "openai" else "max_tokens"
    body = {
        "model": model,
        "messages": messages,
        "stream": True,
        token_field: _max_tokens(provider),
    }
    encoded = json.dumps(body).encode("utf-8")
    lines = iter_lines(
        "POST",
        join_url(_base(provider), "chat/completions"),
        headers=_auth_headers(provider),
        body=encoded,
        cancel=cancel,
    )
    for event in iter_sse_json(lines):
        text = _openai_delta(event)
        if text:
            yield text


def _iter_anthropic(provider: dict[str, Any], messages: list[dict[str, str]], model: str, cancel: threading.Event) -> Iterator[str]:
    token = require_credentials(provider)
    system, rest = _split_system(messages)
    conv = _merge_roles(rest, "assistant")
    if not conv:
        raise ValueError("Nothing to send")
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": _max_tokens(provider),
        "messages": conv,
        "stream": True,
    }
    if system:
        body["system"] = system
    headers = {
        "Content-Type": "application/json",
        "x-api-key": token,
        "anthropic-version": ANTHROPIC_VERSION,
        "Accept": "text/event-stream",
    }
    lines = iter_lines(
        "POST",
        join_url(_base(provider), "v1/messages"),
        headers=headers,
        body=json.dumps(body).encode("utf-8"),
        cancel=cancel,
    )
    for event in iter_sse_json(lines):
        if not isinstance(event, dict):
            continue
        if event.get("type") == "error":
            detail = event.get("error")
            message = detail.get("message") if isinstance(detail, dict) else detail
            raise HttpError(400, redact(str(message or "Anthropic returned an error"))[:400])
        if event.get("type") != "content_block_delta":
            continue
        delta = event.get("delta") or {}
        if isinstance(delta, dict) and isinstance(delta.get("text"), str):
            yield delta["text"]


def _iter_gemini(provider: dict[str, Any], messages: list[dict[str, str]], model: str, cancel: threading.Event) -> Iterator[str]:
    system, rest = _split_system(messages)
    contents = []
    for message in _merge_roles(rest, "model"):
        role = "model" if message["role"] == "model" else "user"
        contents.append({"role": role, "parts": [{"text": message["content"]}]})
    if not contents:
        raise ValueError("Nothing to send")
    body: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {"maxOutputTokens": _max_tokens(provider)},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    safe_model = urllib.parse.quote(model, safe="")
    url = join_url(_base(provider), f"models/{safe_model}:streamGenerateContent?alt=sse")
    lines = iter_lines(
        "POST",
        url,
        headers=_gemini_headers(provider),
        body=json.dumps(body).encode("utf-8"),
        cancel=cancel,
    )
    for event in iter_sse_json(lines):
        if not isinstance(event, dict):
            continue
        error = event.get("error")
        if isinstance(error, dict):
            raise HttpError(400, redact(str(error.get("message") or error))[:400])
        candidates = event.get("candidates") or []
        if not candidates or not isinstance(candidates[0], dict):
            continue
        parts = ((candidates[0].get("content") or {}).get("parts") or [])
        for part in parts:
            if isinstance(part, dict) and isinstance(part.get("text"), str) and part["text"]:
                yield part["text"]


def _iter_ollama(provider: dict[str, Any], messages: list[dict[str, str]], model: str, cancel: threading.Event) -> Iterator[str]:
    body = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {"num_predict": _max_tokens(provider)},
    }
    lines = iter_lines(
        "POST",
        join_url(_base(provider), "api/chat"),
        headers=_auth_headers(provider),
        body=json.dumps(body).encode("utf-8"),
        cancel=cancel,
    )
    for event in iter_json_lines(lines):
        if not isinstance(event, dict):
            continue
        if event.get("error"):
            raise HttpError(400, redact(str(event["error"]))[:400])
        message = event.get("message") or {}
        if isinstance(message, dict) and isinstance(message.get("content"), str) and message["content"]:
            yield message["content"]
        if event.get("done"):
            return
