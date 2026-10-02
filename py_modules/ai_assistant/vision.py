"""Screen-help intent, Jarvis prompt, and which models can take an image."""

from __future__ import annotations

import base64
import re
from typing import Any

SCREEN_PHRASES = (
    "how do i do this",
    "what am i looking at",
    "help me with this",
    "what should i do here",
    "what's on my screen",
    "what is on my screen",
    "what's this",
    "what is this",
    "look at my screen",
    "look at the screen",
    "what should i do",
)

DEFAULT_QUESTION = "What am I looking at, and what should I do next?"

_VISION_HINTS = (
    "gpt-4o",
    "gpt-4.1",
    "gpt-5",
    "claude-3",
    "claude-sonnet",
    "claude-opus",
    "claude-haiku",
    "gemini",
    "grok-4",
    "grok-vision",
    "llava",
    "qwen-vl",
    "qwen2-vl",
    "qwen2.5-vl",
    "pixtral",
    "moondream",
    "internvl",
    "vision",
)
_NOT_VISION = ("embedding", "whisper", "tts", "dall-e", "moderation", "transcribe", "audio")


def wants_screen_look(text: str) -> bool:
    cleaned = re.sub(r"[^a-z0-9' ]+", " ", str(text or "").lower())
    cleaned = " ".join(cleaned.split())
    return any(phrase in cleaned for phrase in SCREEN_PHRASES)


def model_sees_images(model_id: str) -> bool:
    lower = str(model_id or "").lower()
    if not lower or any(word in lower for word in _NOT_VISION):
        return False
    if any(hint in lower for hint in _VISION_HINTS):
        return True
    return "sonnet" in lower or "opus" in lower


def vision_ids(models: list[str]) -> list[str]:
    return [model for model in models if model_sees_images(model)]


def jarvis_prompt(game: str) -> str:
    name = " ".join(str(game or "").split()) or "no game detected"
    return (
        "You are Jarvis, a concise companion on a Steam Deck. "
        f"The person is playing: {name}. "
        "They shared a screenshot and a short question. "
        "Answer in two or three short spoken sentences. "
        "Be friendly, specific to the screenshot, and useful. "
        "Do not use markdown, labels, or a preamble. "
        "Do not spoil anything that is not already on screen."
    )


def _b64(image: bytes) -> str:
    return base64.b64encode(image).decode("ascii")


def openai_messages(messages: list[dict[str, Any]], image: bytes | None) -> list[dict[str, Any]]:
    if not image:
        return messages
    encoded = "data:image/jpeg;base64," + _b64(image)
    updated = [dict(item) for item in messages]
    for index in range(len(updated) - 1, -1, -1):
        content = updated[index].get("content")
        if updated[index].get("role") == "user" and isinstance(content, str):
            updated[index]["content"] = [
                {"type": "text", "text": content},
                {"type": "image_url", "image_url": {"url": encoded}},
            ]
            break
    return updated


def anthropic_messages(messages: list[dict[str, Any]], image: bytes | None) -> list[dict[str, Any]]:
    if not image:
        return messages
    encoded = _b64(image)
    updated = [dict(item) for item in messages]
    for index in range(len(updated) - 1, -1, -1):
        content = updated[index].get("content")
        if updated[index].get("role") == "user" and isinstance(content, str):
            updated[index]["content"] = [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": encoded}},
                {"type": "text", "text": content},
            ]
            break
    return updated


def gemini_parts(text: str, image: bytes | None) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = [{"text": text}]
    if image:
        parts.insert(0, {"inlineData": {"mimeType": "image/jpeg", "data": _b64(image)}})
    return parts


def ollama_messages(messages: list[dict[str, Any]], image: bytes | None) -> list[dict[str, Any]]:
    if not image:
        return messages
    encoded = _b64(image)
    updated = [dict(item) for item in messages]
    for index in range(len(updated) - 1, -1, -1):
        if updated[index].get("role") == "user":
            updated[index]["images"] = [encoded]
            break
    return updated
