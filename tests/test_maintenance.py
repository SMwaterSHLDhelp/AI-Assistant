"""Checks for the release notes, Dependabot auto-merge rules, and drift reporting."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release_notes = _load("release_notes", ROOT / "scripts" / "release_notes.py")
automerge = _load("dependabot_automerge", ROOT / "scripts" / "dependabot_automerge.py")
drift = _load("decky_drift_issue", ROOT / "scripts" / "decky_drift_issue.py")
decky_cli = _load("install_latest_decky_cli", ROOT / "scripts" / "install_latest_decky_cli.py")


def test_release_notes_use_the_changelog_section() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    notes = release_notes.notes_for(changelog, "v0.1.0-rc.3", "ignored")
    assert notes.startswith("## [0.1.0-rc.3]")
    assert "Add provider" in notes
    assert "## [0.1.0-rc.2]" not in notes


def test_release_notes_fall_back_when_the_version_is_missing() -> None:
    notes = release_notes.notes_for("# Changelog\n", "v9.9.9", "- add a thing")
    assert "No matching section" in notes
    assert "- add a thing" in notes


def test_minor_and_patch_updates_can_merge_and_majors_cannot() -> None:
    assert automerge.eligible("Bump the npm-minor-patch group with 2 updates", "")
    assert automerge.eligible("Bump pytest from 9.1.1 to 9.1.2", "")
    assert automerge.eligible("Bump ruff from 0.16.10 to 0.17.0", "")
    assert not automerge.eligible("Bump the npm-major group with 1 update", "")
    assert not automerge.eligible("Bump typescript from 5.6.2 to 6.0.0", "")
    grouped = "Bump the npm-minor-patch group with 1 update"
    body = "Updates `@decky/ui` from 4.12.0 to 5.0.0"
    assert not automerge.eligible(grouped, body)
    assert not automerge.eligible("Bump something", "no versions here")


def test_automerge_waits_for_unfinished_checks_and_skips_failures() -> None:
    success = [{"name": "build", "status": "completed", "conclusion": "success"}]
    assert automerge.readiness(success, {"total_count": 0}) == "merge"
    pending = [{"name": "build", "status": "in_progress", "conclusion": ""}]
    assert automerge.readiness(pending, {"total_count": 0}) == "wait"
    failed = [{"name": "build", "status": "completed", "conclusion": "failure"}]
    assert automerge.readiness(failed, {"total_count": 0}) == "skip"
    assert automerge.readiness([], {"total_count": 0}) == "wait"
    assert automerge.readiness(success, {"total_count": 1, "state": "pending"}) == "wait"


def test_drift_issue_body_includes_the_run_and_log_tail() -> None:
    body = drift.issue_body("failure", "https://example.test/run/1", "x" * 7000)
    assert "https://example.test/run/1" in body
    assert "@decky/ui" in body
    assert len(body) < 7000
    closed = drift.issue_body("success", "https://example.test/run/2", "")
    assert "passed" in closed


def test_decky_cli_asset_name_is_required() -> None:
    release = {"assets": [{"name": "decky-linux-x86_64", "browser_download_url": "https://example.test/decky"}]}
    assert decky_cli.linux_asset_url(release) == "https://example.test/decky"
    try:
        decky_cli.linux_asset_url({"assets": [{"name": "other"}]})
    except SystemExit as exc:
        assert "decky-linux-x86_64" in str(exc)
    else:
        raise AssertionError("missing asset should fail")


def test_dependabot_groups_match_the_automerge_rule() -> None:
    text = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    for name in ("npm-minor-patch", "pip-minor-patch", "actions-minor-patch"):
        assert name in text
    assert "package-ecosystem: npm" in text
    assert "package-ecosystem: pip" in text
    assert "package-ecosystem: github-actions" in text
