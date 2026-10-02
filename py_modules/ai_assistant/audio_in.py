"""Capture the Deck user's microphone from a plugin process that may be running as root."""

from __future__ import annotations

import os
from collections.abc import Callable

Which = Callable[[str], str | None]


def deck_uid() -> int:
    try:
        import pwd

        return int(pwd.getpwnam("deck").pw_uid)
    except (KeyError, ImportError):
        return 1000


def deck_audio_env(euid: int | None = None, uid: int | None = None) -> dict[str, str]:
    """Pulse and PipeWire sockets live under the deck user's runtime dir, not root's."""
    current = os.geteuid() if euid is None else euid
    user_id = uid if uid is not None else (deck_uid() if current == 0 else os.getuid())
    runtime = f"/run/user/{user_id}"
    if current != 0 and os.environ.get("XDG_RUNTIME_DIR"):
        runtime = os.environ["XDG_RUNTIME_DIR"]
    env = {key: value for key, value in os.environ.items() if key != "LD_LIBRARY_PATH"}
    env["XDG_RUNTIME_DIR"] = runtime
    env["PULSE_SERVER"] = f"unix:{runtime}/pulse/native"
    if current == 0:
        env["HOME"] = "/home/deck"
        env["USER"] = "deck"
        env["LOGNAME"] = "deck"
    return env


def capture_command(which: Which, euid: int | None = None) -> tuple[list[str], dict[str, str]]:
    current = os.geteuid() if euid is None else euid
    env = deck_audio_env(current)
    if which("parec"):
        argv = ["parec", "--raw", "--rate=16000", "--channels=1", "--format=s16le", "--latency-msec=50"]
    elif which("pw-record"):
        argv = ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16", "-"]
    elif which("pw-cat"):
        argv = ["pw-cat", "--record", "--format", "s16", "--rate", "16000", "--channels", "1", "-"]
    else:
        raise RuntimeError("Could not find parec or pw-record. Voice control needs the Deck's PipeWire session.")
    if current == 0:
        if not which("runuser"):
            raise RuntimeError("Deckling is running as root and cannot switch to the deck user for the microphone.")
        argv = ["runuser", "-u", "deck", "--preserve-environment", "--", *argv]
    return argv, env
