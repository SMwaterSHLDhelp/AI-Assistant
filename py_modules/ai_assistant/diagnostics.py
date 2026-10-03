"""In-memory plugin log and a file the user can open without SSH."""

from __future__ import annotations

import os
from collections import deque

_LINES: deque[str] = deque(maxlen=30)


def remember(line: str) -> None:
    text = " ".join(str(line or "").split())
    if text:
        _LINES.append(text[:400])


def snapshot() -> list[str]:
    return list(_LINES)


def diagnostics_path() -> str:
    home = os.environ.get("DECKY_USER_HOME") or os.path.expanduser("~")
    return os.path.join(home, "Deckling-diagnostics.txt")


def write_report(path: str, lines: list[str], header: str) -> str:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    body = header.rstrip() + "\n" + "\n".join(lines) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, body.encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(path, 0o600)
    return path
