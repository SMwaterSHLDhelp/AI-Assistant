"""Print GitHub Release notes for one version tag.

The tag workflow uses this so the release body matches CHANGELOG.md.
When that version has no section yet, the notes fall back to the commit subjects
since the previous tag.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def extract_section(changelog: str, version: str) -> str:
    bare = version[1:] if version.startswith("v") else version
    heading = f"## [{bare}]"
    lines = changelog.splitlines()
    start = next((index for index, line in enumerate(lines) if line.startswith(heading)), None)
    if start is None:
        return ""
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    text = "\n".join(lines[start:end]).strip()
    return f"{text}\n" if text else ""


def commits_since_previous_tag(version: str) -> str:
    try:
        previous = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0", f"{version}^"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        revision = f"{previous}..{version}"
    except subprocess.CalledProcessError:
        revision = version
    log = subprocess.check_output(
        ["git", "log", "--no-merges", "--pretty=format:- %s", revision],
        text=True,
        stderr=subprocess.DEVNULL,
    )
    return log.strip()


def notes_for(changelog: str, version: str, commits: str) -> str:
    section = extract_section(changelog, version)
    if section:
        return section
    body = f"Release {version}\n\nNo matching section in CHANGELOG.md.\n"
    if commits.strip():
        body += "\nCommits since the previous tag:\n\n" + commits.strip() + "\n"
    return body


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: release_notes.py v0.1.0-rc.3", file=sys.stderr)
        return 2
    version = argv[1]
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    sys.stdout.write(notes_for(changelog, version, commits_since_previous_tag(version)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
