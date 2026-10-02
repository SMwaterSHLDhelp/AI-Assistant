import re
from pathlib import Path

from ai_assistant.catalog import KINDS
from ai_assistant.service import AssistantService


def test_frontend_catalog_matches_backend() -> None:
    text = Path("src/catalog.ts").read_text(encoding="utf-8")
    found = re.findall(r'kind: "([^"]+)"', text)
    assert found == list(KINDS)


def test_state_keeps_the_catalog_when_chats_cannot_be_read(tmp_path) -> None:
    service = AssistantService(str(tmp_path / "settings"), str(tmp_path / "runtime"))
    service.store.ensure_session()
    with open(service.store.sessions_path, "w", encoding="utf-8") as handle:
        handle.write("{")
    result = service.state()
    assert result["ok"] is False
    assert "chats" in result["error"]
    assert any(item["kind"] == "llamacpp" for item in result["catalog"])
