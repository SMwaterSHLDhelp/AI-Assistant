"""Per-game chat groups. Titles are shortened on this Deck, without a model call."""

from __future__ import annotations

from typing import Any

KEEP_CHOICES = (20, 40, 80)
DEFAULT_KEEP = 40


def normalize_chats(raw: Any) -> dict[str, Any]:
    keep = DEFAULT_KEEP
    remember = True
    if isinstance(raw, dict):
        try:
            keep = int(raw.get("keep") or DEFAULT_KEEP)
        except (TypeError, ValueError):
            keep = DEFAULT_KEEP
        if keep not in KEEP_CHOICES:
            keep = min(KEEP_CHOICES, key=lambda choice: abs(choice - keep))
        if "remember_model" in raw:
            remember = bool(raw["remember_model"])
    return {"keep": keep, "remember_model": remember}


def game_bucket(game: dict[str, Any] | None) -> tuple[str, str]:
    """Stable group id and the label shown in the chat list."""
    if not isinstance(game, dict):
        return "general", "General"
    name = " ".join(str(game.get("name") or "").split())[:80]
    if not name:
        return "general", "General"
    if game.get("shortcut") or game.get("rom"):
        return "rom:" + name.casefold(), name
    try:
        appid = int(game.get("appid") or 0)
    except (TypeError, ValueError):
        appid = 0
    if appid > 0:
        return f"app:{appid}", name
    return "name:" + name.casefold(), name


def chat_title(text: str) -> str:
    cleaned = str(text or "").strip()
    if cleaned.startswith("[Playing:") and "\n\n" in cleaned:
        cleaned = cleaned.split("\n\n", 1)[1].strip()
    if cleaned.startswith("[Looking at the screen]"):
        cleaned = cleaned.replace("[Looking at the screen]", "", 1).strip()
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return "New chat"
    if len(cleaned) > 42:
        return cleaned[:42].rstrip() + "…"
    return cleaned


def preview_text(messages: list[dict[str, Any]]) -> str:
    if not messages:
        return ""
    text = " ".join(str(messages[-1].get("content") or "").split())
    if len(text) > 80:
        return text[:80].rstrip() + "…"
    return text


def prune_sessions(sessions: list[dict[str, Any]], keep: int, current_id: str) -> list[dict[str, Any]]:
    """Drop the oldest unpinned chats past the cap. The open chat stays."""
    limit = normalize_chats({"keep": keep})["keep"]
    pinned = [item for item in sessions if item.get("pinned")]
    rest = [item for item in sessions if not item.get("pinned")]
    rest.sort(key=lambda item: int(item.get("updated_at") or 0), reverse=True)
    kept = pinned + rest
    if len(kept) <= limit:
        return sessions
    chosen = kept[:limit]
    ids = {item.get("id") for item in chosen}
    if current_id and current_id not in ids:
        current = next((item for item in sessions if item.get("id") == current_id), None)
        if current is not None:
            chosen.append(current)
    chosen_ids = {item.get("id") for item in chosen}
    return [item for item in sessions if item.get("id") in chosen_ids]


def sort_sessions(sessions: list[dict[str, Any]], active_key: str) -> list[dict[str, Any]]:
    """Current game, then other games newest-first, then General."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in sessions:
        groups.setdefault(str(item.get("game_key") or "general"), []).append(item)
    keys: list[str] = []
    if active_key in groups:
        keys.append(active_key)
    others = [key for key in groups if key not in {active_key, "general"}]
    others.sort(
        key=lambda key: max(int(item.get("updated_at") or 0) for item in groups[key]),
        reverse=True,
    )
    keys.extend(others)
    if "general" in groups and active_key != "general":
        keys.append("general")
    ordered: list[dict[str, Any]] = []
    for key in keys:
        rows = groups[key]
        rows.sort(key=lambda item: (not bool(item.get("pinned")), -int(item.get("updated_at") or 0)))
        ordered.extend(rows)
    return ordered
