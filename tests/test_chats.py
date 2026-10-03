"""Per-game chats: migration, rename, grouping, and the history cap."""

from __future__ import annotations

import json
import os
import stat

from ai_assistant.chats import chat_title, sort_sessions
from ai_assistant.service import AssistantService
from ai_assistant.store import Store


def test_legacy_sessions_move_into_one_file_per_chat(tmp_path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    legacy = {
        "current_id": "abc",
        "sessions": [
            {
                "id": "abc",
                "title": "Old chat",
                "updated_at": 10,
                "messages": [{"id": "m1", "role": "user", "content": "Hello", "created_at": 10}],
                "claude_session_id": "sess-old",
            }
        ],
    }
    (runtime / "sessions.json").write_text(json.dumps(legacy), encoding="utf-8")
    store = Store(str(tmp_path / "settings"), str(runtime))
    data = store.load_sessions()
    assert data["current_id"] == "abc"
    assert data["sessions"][0]["messages"][0]["content"] == "Hello"
    assert data["sessions"][0]["game_key"] == "general"
    chat_path = runtime / "chats" / "abc.json"
    assert json.loads(chat_path.read_text(encoding="utf-8"))["messages"][0]["content"] == "Hello"
    assert stat.S_IMODE(chat_path.stat().st_mode) == 0o600
    assert stat.S_IMODE((runtime / "sessions.json").stat().st_mode) == 0o600
    assert "messages" not in json.loads((runtime / "sessions.json").read_text(encoding="utf-8"))["sessions"][0]
    again = store.load_sessions()
    assert len(again["sessions"]) == 1


def test_rename_sticks_and_the_first_question_names_a_new_chat(tmp_path) -> None:
    store = Store(str(tmp_path / "settings"), str(tmp_path / "runtime"))
    created = store.new_session("app:1245620", "Elden Ring")
    store.append_message(created["id"], "user", "[Playing: Elden Ring]\n\nWhere is the grace?")
    loaded = store.load_sessions()["sessions"][0]
    assert loaded["title"] == "Where is the grace?"
    renamed = store.rename_session(created["id"], "Boss route")
    assert renamed["title"] == "Boss route"
    store.append_message(created["id"], "user", "A totally different question about a cave")
    assert store.load_sessions()["sessions"][0]["title"] == "Boss route"
    assert chat_title("  hi   there  ") == "hi there"


def test_focus_opens_the_newest_chat_for_that_game(tmp_path) -> None:
    service = AssistantService(str(tmp_path / "settings"), str(tmp_path / "runtime"))
    general = service.store.new_session()
    service.store.append_message(general["id"], "user", "Deck question")
    first = service.set_game_context({"appid": 1245620, "name": "Elden Ring", "sources": ["router"]})
    assert first["focused"] is True
    assert first["game"]["game_key"] == "app:1245620"
    elden = first["current_session_id"]
    service.store.append_message(elden, "user", "First elden chat")
    second = service.store.new_session("app:1245620", "Elden Ring")
    service.store.append_message(second["id"], "user", "Newer elden chat")
    service.store.switch_session(general["id"])
    again = service.set_game_context({"appid": 1091500, "name": "Cyberpunk 2077"})
    assert again["focused"] is True
    assert again["sessions"][0]["game_key"] == "app:1091500"
    back = service.set_game_context({"appid": 1245620, "name": "Elden Ring"})
    assert back["current_session_id"] == second["id"]
    same = service.set_game_context({"appid": 1245620, "name": "Elden Ring", "rich_presence": "Limgrave"})
    assert same["focused"] is False
    ordered = sort_sessions(service.store.load_sessions()["sessions"], "app:1245620")
    assert ordered[0]["game_key"] == "app:1245620"
    assert ordered[-1]["game_key"] == "general"


def test_pin_survives_the_cap_and_model_memory_is_optional(tmp_path) -> None:
    service = AssistantService(str(tmp_path / "settings"), str(tmp_path / "runtime"))
    service.save_chats({"keep": 20})
    pinned = service.store.new_session()
    service.store.append_message(pinned["id"], "user", "Keep me")
    service.store.pin_session(pinned["id"], True)
    for index in range(25):
        chat = service.store.new_session()
        service.store.append_message(chat["id"], "user", f"Note {index}")
    left = {item["id"] for item in service.store.load_sessions()["sessions"]}
    assert pinned["id"] in left
    assert len(left) <= 21
    saved = service.save_provider(
        {"kind": "custom", "name": "Local", "base_url": "http://127.0.0.1:9/v1", "default_model": "m"}
    )
    service.store.remember_model(pinned["id"], saved["provider"]["id"], "chosen-model")
    opened = service.switch_session(pinned["id"])
    assert opened["model"] == "chosen-model"
    assert opened["remember_model"] is True
    service.save_chats({"remember_model": False})
    service.store.remember_model(pinned["id"], saved["provider"]["id"], "other-model")
    assert service.switch_session(pinned["id"])["model"] == "chosen-model"
    moved = service.move_session(pinned["id"], "rom:chrono trigger", "Chrono Trigger")
    match = next(item for item in moved["sessions"] if item["id"] == pinned["id"])
    assert match["game_key"] == "rom:chrono trigger"
    assert os.path.isdir(service.store.runtime_dir)
