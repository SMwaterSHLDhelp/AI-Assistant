"""Capture the current game picture on SteamOS without keeping it on disk.

Order: a gamescope control socket, then a gamescope PipeWire video node, then a
screenshot file gamescope or Steam just wrote under the temp directory. The
Quick Access Menu has to be closed first so the overlay is not in the shot.
"""

from __future__ import annotations

import base64
import binascii
import glob
import json
import os
import socket
import stat
import subprocess
import time
from collections.abc import Callable
from typing import Any

Runner = Callable[[list[str]], str]


class CaptureError(Exception):
    pass


class CaptureContext:
    def __init__(
        self,
        *,
        runtime_dir: str,
        tmp_dir: str,
        env: dict[str, str],
        run: Runner,
        timeout: float,
        started: float,
    ) -> None:
        self.runtime_dir = runtime_dir
        self.tmp_dir = tmp_dir
        self.env = env
        self.run = run
        self.timeout = timeout
        self.started = started


def capture_screen(
    *,
    qam_hidden: bool,
    enabled: bool,
    runtime_dir: str,
    grabbers: list[Callable[[CaptureContext], bytes | None]] | None = None,
    env: dict[str, str] | None = None,
    run: Runner | None = None,
    tmp_dir: str = "/tmp",
    timeout: float = 2.0,
    started: float | None = None,
) -> bytes:
    if not enabled:
        raise CaptureError("Screen capture is turned off in settings.")
    if not qam_hidden:
        raise CaptureError("Hide the Quick Access Menu before taking the shot.")
    context = CaptureContext(
        runtime_dir=runtime_dir,
        tmp_dir=tmp_dir,
        env=dict(env or os.environ),
        run=run or _default_run,
        timeout=timeout,
        started=time.time() if started is None else started,
    )
    steps = grabbers or [grab_gamescope, grab_pipewire, grab_recent_file]
    for grab in steps:
        data = grab(context)
        if data:
            return data
    raise CaptureError("Could not capture the game screen. Gamescope, Steam, and PipeWire did not return a shot.")


def grab_gamescope(context: CaptureContext) -> bytes | None:
    runtime = context.env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    if not os.path.isdir(runtime):
        return None
    sockets = []
    for name in os.listdir(runtime):
        if "gamescope" not in name:
            continue
        path = os.path.join(runtime, name)
        try:
            if stat.S_ISSOCK(os.stat(path).st_mode):
                sockets.append(path)
        except OSError:
            continue
    if not sockets:
        return None
    dest = os.path.join(context.tmp_dir, f"gamescope-deckling-{os.getpid()}.png")
    for sock_path in sockets:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(context.timeout)
                client.connect(sock_path)
                client.sendall(f"screenshot {dest}\n".encode())
                try:
                    client.recv(512)
                except TimeoutError:
                    pass
        except OSError:
            continue
        found = _wait_for_file(dest, context.timeout)
        if found:
            unlink_temp(dest, context)
            return found
    unlink_temp(dest, context)
    return None


def grab_pipewire(context: CaptureContext) -> bytes | None:
    try:
        dumped = context.run(["pw-dump"])
        nodes = json.loads(dumped)
    except (OSError, json.JSONDecodeError, subprocess.SubprocessError):
        return None
    node_id = _gamescope_video_node(nodes)
    if node_id is None:
        return None
    dest = os.path.join(context.tmp_dir, f"gamescope-pw-{os.getpid()}.png")
    try:
        context.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "pipewire", "-i", str(node_id), "-frames:v", "1", dest])
    except (OSError, subprocess.SubprocessError):
        unlink_temp(dest, context)
        return None
    if not os.path.isfile(dest):
        return None
    try:
        with open(dest, "rb") as handle:
            data = handle.read()
    except OSError:
        return None
    finally:
        unlink_temp(dest, context)
    return data if _looks_like_image(data) else None


def grab_recent_file(context: CaptureContext) -> bytes | None:
    newest: str | None = None
    newest_mtime = context.started - 0.05
    for pattern in ("gamescope*.png", "steam*.png"):
        for path in glob.glob(os.path.join(context.tmp_dir, pattern)):
            try:
                info = os.stat(path)
            except OSError:
                continue
            if info.st_mtime >= newest_mtime and info.st_size > 24:
                newest = path
                newest_mtime = info.st_mtime
    if newest is None:
        return None
    try:
        with open(newest, "rb") as handle:
            data = handle.read()
    except OSError:
        return None
    if os.path.basename(newest).startswith("gamescope"):
        unlink_temp(newest, context)
    return data if _looks_like_image(data) else None


def decode_supplied_image(value: str, runtime_dir: str, *, tmp_dir: str = "/tmp") -> bytes:
    text = str(value or "").strip()
    if not text:
        raise CaptureError("The screenshot was empty.")
    if text.startswith("data:"):
        comma = text.find(",")
        if comma < 0:
            raise CaptureError("Could not read that screenshot.")
        text = text[comma + 1 :]
    if text.startswith("/"):
        return _read_allowed_path(text, runtime_dir, tmp_dir)
    try:
        data = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CaptureError("Could not read that screenshot.") from exc
    if len(data) > 8_000_000:
        raise CaptureError("That screenshot is too large to send.")
    if not _looks_like_image(data):
        raise CaptureError("Could not read that screenshot.")
    return data


def unlink_temp(path: str, context: CaptureContext) -> None:
    """Delete a capture we created. Never touch Steam's userdata screenshots."""
    try:
        real = os.path.realpath(path)
    except OSError:
        return
    roots = [os.path.realpath(context.tmp_dir), os.path.realpath(context.runtime_dir)]
    if not any(real == root or real.startswith(root + os.sep) for root in roots):
        return
    try:
        os.remove(real)
    except OSError:
        pass


def _gamescope_video_node(nodes: Any) -> object | None:
    if not isinstance(nodes, list):
        return None
    for node in nodes:
        if not isinstance(node, dict):
            continue
        info = node.get("info")
        props = info.get("props") if isinstance(info, dict) else None
        if not isinstance(props, dict):
            continue
        name = " ".join(
            str(props.get(key) or "") for key in ("node.name", "node.description", "application.name")
        ).lower()
        media = str(props.get("media.class") or "")
        if "gamescope" in name and "Video" in media:
            return node.get("id")
    return None


def _wait_for_file(path: str, timeout: float) -> bytes | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.isfile(path) and os.path.getsize(path) > 24:
            try:
                with open(path, "rb") as handle:
                    data = handle.read()
            except OSError:
                return None
            if _looks_like_image(data):
                return data
        time.sleep(0.05)
    return None


def _read_allowed_path(path: str, runtime_dir: str, tmp_dir: str) -> bytes:
    real = os.path.realpath(path)
    roots = [os.path.realpath(tmp_dir), os.path.realpath(runtime_dir)]
    home = os.path.expanduser("~")
    for extra in (
        os.path.join(home, ".local", "share", "Steam", "userdata"),
        os.path.join(home, ".steam", "steam", "userdata"),
    ):
        if os.path.isdir(extra):
            roots.append(os.path.realpath(extra))
    if not any(real == root or real.startswith(root + os.sep) for root in roots):
        raise CaptureError("Could not read that screenshot.")
    try:
        with open(real, "rb") as handle:
            data = handle.read(8_000_001)
    except OSError as exc:
        raise CaptureError("Could not read that screenshot.") from exc
    if len(data) > 8_000_000 or not _looks_like_image(data):
        raise CaptureError("Could not read that screenshot.")
    context = CaptureContext(
        runtime_dir=runtime_dir,
        tmp_dir=tmp_dir,
        env={},
        run=_default_run,
        timeout=0,
        started=0,
    )
    unlink_temp(real, context)
    return data


def _looks_like_image(data: bytes) -> bool:
    return data.startswith(b"\x89PNG") or data.startswith(b"\xff\xd8")


def _default_run(args: list[str]) -> str:
    completed = subprocess.run(args, check=False, capture_output=True, timeout=8)
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace")[:200]
        raise OSError(detail or f"{args[0]} failed")
    return completed.stdout.decode("utf-8", "replace")
