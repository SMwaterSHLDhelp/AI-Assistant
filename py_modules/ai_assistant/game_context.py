"""Compact context for the game that is running, cached per Steam app id."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from .chats import game_bucket
from .http_util import USER_AGENT

STORE_URL = "https://store.steampowered.com/api/appdetails?appids={appid}&l=english"
CACHE_SECONDS = 7 * 24 * 60 * 60
SHORTCUT_APPID = 2_000_000_000
ROM_EXTENSIONS = (
    "nsp",
    "xci",
    "iso",
    "cue",
    "chd",
    "gba",
    "gbc",
    "gb",
    "nes",
    "smc",
    "sfc",
    "z64",
    "n64",
    "nds",
    "3ds",
    "cia",
    "wbfs",
    "rvz",
    "wad",
    "pbp",
    "bin",
    "md",
    "sms",
    "gg",
    "pce",
    "cdi",
    "gdi",
    "wux",
    "wua",
    "cso",
    "dsk",
)
EMULATORS = {
    "retroarch",
    "emudeck",
    "yuzu",
    "ryujinx",
    "cemu",
    "dolphin",
    "pcsx2",
    "rpcs3",
    "duckstation",
    "ppsspp",
    "melonds",
    "citra",
    "azahar",
    "primehack",
    "xemu",
    "mgba",
    "snes9x",
    "nestopia",
    "mame",
    "flycast",
    "xenia",
    "steamrommanager",
}
_EXT = "|".join(ROM_EXTENSIONS)
_ROM_PATTERN = re.compile(
    rf'(?:"([^"]+\.(?:{_EXT}))"|'
    rf"'([^']+\.(?:{_EXT}))'|"
    rf"(\S+\.(?:{_EXT})))",
    re.IGNORECASE,
)
Fetcher = Callable[[str], bytes]


def normalize_context(raw: Any) -> dict[str, Any]:
    prefs = {"share_game_context": True, "include_achievements": True, "include_playtime": True}
    if isinstance(raw, dict):
        for key in prefs:
            if key in raw:
                prefs[key] = bool(raw[key])
    return prefs


def rom_title(name: str, exe: str, launch_options: str) -> str:
    """Pull an emulated game title out of a shortcut command line."""
    matches = _ROM_PATTERN.findall(f"{launch_options or ''} {exe or ''}")
    if not matches:
        return ""
    path = next(part for part in matches[-1] if part)
    base = os.path.basename(path.replace("\\", "/"))
    stem = base.rsplit(".", 1)[0]
    title = re.sub(r"[_\.]+", " ", stem)
    title = re.sub(r"\s+", " ", title).strip(" -")
    return title[:120]


def _emulator_name(name: str, exe: str) -> str:
    blob = f"{name} {exe}".lower()
    for item in sorted(EMULATORS, key=len, reverse=True):
        if item in blob:
            return item
    return ""


def _number(value: Any) -> int | None:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return number


def _text(value: Any, limit: int = 180) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def prepare_snapshot(snapshot: dict[str, Any], now: float | None = None) -> dict[str, Any]:
    """Turn a Steam client snapshot into the fields the prompt and the card share."""
    clock = time.time() if now is None else now
    appid = _number(snapshot.get("appid")) or 0
    shortcut = bool(snapshot.get("shortcut")) or appid >= SHORTCUT_APPID
    name = _text(snapshot.get("name"), 120)
    exe = _text(snapshot.get("exe"), 200)
    options = _text(snapshot.get("launch_options"), 300)
    rom = rom_title(name, exe, options) if shortcut or _emulator_name(name, exe) else ""
    emulator = _emulator_name(name, exe) if shortcut or rom else ""
    display = rom or name
    started = _number(snapshot.get("session_started"))
    session_minutes = None
    if started:
        session_minutes = max(0, int((clock - started) / 60))
    last_played = _number(snapshot.get("last_played"))
    return {
        "appid": appid,
        "name": display,
        "shortcut_name": name if rom and name and name != display else "",
        "shortcut": shortcut,
        "rom": rom,
        "emulator": emulator,
        "exe": exe,
        "rich_presence": _text(snapshot.get("rich_presence"), 160),
        "playtime_minutes": _number(snapshot.get("playtime_minutes")),
        "session_minutes": session_minutes,
        "last_played": last_played,
        "achievements_unlocked": _number(snapshot.get("achievements_unlocked")),
        "achievements_total": _number(snapshot.get("achievements_total")),
        "recent_achievements": [_text(item, 80) for item in (snapshot.get("recent_achievements") or []) if _text(item, 80)][:3],
        "next_achievement": _text(snapshot.get("next_achievement"), 80),
        "compat_tool": _text(snapshot.get("compat_tool"), 80),
        "recent_screenshot": bool(snapshot.get("recent_screenshot")),
        "sources": [str(item) for item in (snapshot.get("sources") or [])][:8],
    }


def _hours(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    return f"{hours} hr" if minutes % 60 < 15 else f"{hours} hr {minutes % 60} min"


def format_block(game: dict[str, Any], prefs: dict[str, Any]) -> str:
    """System-prompt block. Unknown fields and opted-out fields are left out."""
    settings = normalize_context(prefs)
    if not settings["share_game_context"]:
        return ""
    name = _text(game.get("name"), 120)
    if not name:
        return ""
    lines = ["Game context:", f"Game: {name}"]
    if game.get("emulator"):
        lines.append(f"Emulator: {game['emulator']}")
    if game.get("shortcut") and game.get("exe"):
        lines.append(f"Shortcut exe: {game['exe']}")
    if game.get("rich_presence"):
        lines.append(f"Status: {game['rich_presence']}")
    if settings["include_playtime"]:
        if game.get("session_minutes") is not None:
            lines.append(f"Session: {_hours(int(game['session_minutes']))}")
        if game.get("playtime_minutes") is not None:
            lines.append(f"Playtime: {_hours(int(game['playtime_minutes']))}")
        if game.get("last_played"):
            lines.append("Last played: " + time.strftime("%Y-%m-%d", time.gmtime(int(game["last_played"]))))
    if settings["include_achievements"] and game.get("achievements_total"):
        unlocked = int(game.get("achievements_unlocked") or 0)
        lines.append(f"Achievements: {unlocked}/{int(game['achievements_total'])}")
        if game.get("recent_achievements"):
            lines.append("Recently unlocked: " + ", ".join(game["recent_achievements"]))
        if game.get("next_achievement"):
            lines.append(f"Next achievement: {game['next_achievement']}")
    if game.get("genres"):
        lines.append("Genres: " + ", ".join(game["genres"][:4]))
    if game.get("developer"):
        lines.append(f"Developer: {game['developer']}")
    if game.get("about"):
        lines.append(f"About: {game['about']}")
    if game.get("compat_tool"):
        lines.append(f"Proton: {game['compat_tool']}")
    if game.get("guide"):
        lines.append(f"Guides: {game['guide']}")
    if game.get("wiki"):
        lines.append(f"Wiki: {game['wiki']}")
    if game.get("recent_screenshot"):
        lines.append("A recent Steam screenshot is available.")
    return "\n".join(lines)[:1500]


def suggestions(game: dict[str, Any]) -> list[str]:
    name = _text(game.get("name"), 80) or "this game"
    prompts = []
    if game.get("rich_presence"):
        prompts.append(f"I'm at {game['rich_presence']}. What should I do next?")
    if game.get("next_achievement"):
        prompts.append(f"How do I unlock {game['next_achievement']}?")
    else:
        prompts.append(f"What achievement should I go for next in {name}?")
    prompts.append(f"Where do I find the next thing I need in {name}?")
    return prompts[:3]


def public_game(game: dict[str, Any]) -> dict[str, Any] | None:
    if not game.get("name"):
        return None
    key, label = game_bucket(game)
    return {
        "appid": int(game.get("appid") or 0),
        "name": game.get("name") or "",
        "rich_presence": game.get("rich_presence") or "",
        "achievements_unlocked": game.get("achievements_unlocked"),
        "achievements_total": game.get("achievements_total"),
        "capsule": game.get("capsule") or "",
        "emulator": game.get("emulator") or "",
        "shortcut": bool(game.get("shortcut")),
        "sources": list(game.get("sources") or []),
        "game_key": key,
        "game_label": label,
    }


def _cache_path(cache_dir: str, appid: int) -> str:
    return os.path.join(cache_dir, f"{appid}.json")


def _read_cache(path: str, now: float) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if now - float(data.get("fetched_at") or 0) > CACHE_SECONDS:
        return None
    return data


def _wiki(name: str) -> str:
    return "https://www.pcgamingwiki.com/wiki/Special:Search?search=" + urllib.parse.quote(name)


def _fetch_store(appid: int, fetch: Fetcher, now: float) -> dict[str, Any] | None:
    """Public store fields, or None when the request failed so a later turn can retry."""
    try:
        payload = json.loads(fetch(STORE_URL.format(appid=appid)).decode("utf-8", "replace"))
    except Exception:
        return None
    entry = payload.get(str(appid)) if isinstance(payload, dict) else None
    if not isinstance(entry, dict) or not entry.get("success"):
        return None
    data = entry.get("data")
    if not isinstance(data, dict):
        return None
    genres = []
    for genre in data.get("genres") or []:
        if isinstance(genre, dict) and genre.get("description"):
            genres.append(_text(genre["description"], 40))
    developers = data.get("developers") or []
    return {
        "fetched_at": now,
        "genres": genres[:4],
        "developer": _text(developers[0], 80) if developers else "",
        "about": _text(data.get("short_description"), 180),
        "capsule": _text(data.get("header_image"), 240),
    }


def _store_fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=8) as response:
        return response.read()


def enrich_store(game: dict[str, Any], cache_dir: str, fetch: Fetcher | None = None, now: float | None = None) -> dict[str, Any]:
    """Add genres, a short description, and the developer. Non-Steam shortcuts are not looked up."""
    appid = int(game.get("appid") or 0)
    if appid <= 0 or game.get("shortcut") or appid >= SHORTCUT_APPID:
        game["wiki"] = _wiki(str(game.get("name") or ""))
        return game
    clock = time.time() if now is None else now
    os.makedirs(cache_dir, exist_ok=True)
    os.chmod(cache_dir, 0o700)
    path = _cache_path(cache_dir, appid)
    cached = _read_cache(path, clock)
    if cached is None:
        cached = _fetch_store(appid, fetch or _store_fetch, clock)
        if cached is None:
            game["guide"] = f"https://steamcommunity.com/app/{appid}/guides/"
            game["wiki"] = _wiki(str(game.get("name") or ""))
            return game
        temporary = path + ".partial"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(cached, handle)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    game["genres"] = list(cached.get("genres") or [])
    game["developer"] = cached.get("developer") or ""
    game["about"] = cached.get("about") or ""
    game["capsule"] = cached.get("capsule") or ""
    game["guide"] = f"https://steamcommunity.com/app/{appid}/guides/"
    game["wiki"] = _wiki(str(game.get("name") or ""))
    return game
