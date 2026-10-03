"""A private CPython for voice models.

SteamOS Python has no pip, and the root filesystem is read-only. The wake
word and speech wheels install into a venv made from python-build-standalone,
downloaded into the plugin data directory and checked before it is unpacked.
"""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import tarfile
from collections.abc import Callable
from pathlib import Path

RELEASE = "20261003"
_BASE = f"https://github.com/astral-sh/python-build-standalone/releases/download/{RELEASE}/"
# install_only includes pip and ensurepip. The stripped build does not.
_BUILDS: dict[str, tuple[str, str]] = {
    "x86_64": (
        "cpython-3.11.17+20261003-x86_64-unknown-linux-gnu-install_only.tar.gz",
        "c624af93ad62a596806bbd2404e1fb80744a407ca7279854445ede16d93858b8",
    ),
    "aarch64": (
        "cpython-3.11.17+20261003-aarch64-unknown-linux-gnu-install_only.tar.gz",
        "2238f0556d3a9777d42261b1e4d7b9834d56f111d3dd879a0647c27c824cc31d",
    ),
    "arm64": (
        "cpython-3.11.17+20261003-aarch64-unknown-linux-gnu-install_only.tar.gz",
        "2238f0556d3a9777d42261b1e4d7b9834d56f111d3dd879a0647c27c824cc31d",
    ),
}

Fetcher = Callable[[str, str, Callable[[str, float], None] | None], None]
Progress = Callable[[str, float], None]


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _find_python(root: str) -> str:
    for dirpath, _dirs, files in os.walk(root):
        if os.path.basename(dirpath) != "bin":
            continue
        for name in ("python3", "python"):
            if name in files:
                return os.path.join(dirpath, name)
    return ""


def _python_ok(path: str) -> bool:
    try:
        completed = subprocess.run(
            [path, "-c", "import sys; raise SystemExit(0 if sys.version_info[0] == 3 else 1)"],
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _inside(root: str, path: str) -> bool:
    root_real = os.path.realpath(root)
    return path == root_real or path.startswith(root_real + os.sep)


def _extract_python(archive: str, root: str) -> None:
    """Unpack python-build-standalone, including its in-tree symlinks.

    Piper archives stay strict. This archive uses ``bin/python -> python3.11``
    and terminfo links that contain ``../`` but stay inside the tree.
    """
    with tarfile.open(archive, "r:gz") as handle:
        members = handle.getmembers()
        for member in members:
            name = member.name
            if not name or name.startswith("/") or name.startswith("\\") or ".." in Path(name).parts:
                raise ValueError("Python archive path is not safe")
            if member.islnk():
                link = member.linkname
                if not link or os.path.isabs(link) or ".." in Path(link).parts:
                    raise ValueError("Python archive path is not safe")
                continue
            if member.issym():
                link = member.linkname
                if not link or os.path.isabs(link):
                    raise ValueError("Python archive path is not safe")
                parent = os.path.normpath(os.path.join(root, os.path.dirname(name)))
                target = os.path.normpath(os.path.join(parent, link))
                if not _inside(root, target):
                    raise ValueError("Python archive path is not safe")
        handle.extractall(root, members=members)


def ensure_runtime_python(
    runtime_dir: str,
    fetch: Fetcher,
    progress: Progress | None = None,
    machine: str | None = None,
) -> str:
    """Return ``bin/python3`` from the private runtime, downloading it once."""
    root = os.path.join(runtime_dir, "python")
    os.makedirs(root, exist_ok=True)
    existing = _find_python(root)
    if existing and _python_ok(existing):
        return existing
    spec = _BUILDS.get(machine or platform.machine())
    if spec is None:
        raise RuntimeError(f"No standalone Python build for {machine or platform.machine()}.")
    filename, digest = spec
    archive = os.path.join(root, filename)
    if not (os.path.isfile(archive) and _sha256(archive) == digest):
        if progress:
            progress("Downloading Python", 0.02)
        fetch(_BASE + filename, archive, progress)
    if _sha256(archive) != digest:
        try:
            os.remove(archive)
        except OSError:
            pass
        raise RuntimeError("The Python download did not match its checksum and was deleted.")
    if progress:
        progress("Unpacking Python", 0.2)
    _extract_python(archive, root)
    found = _find_python(root)
    if not found or not _python_ok(found):
        raise RuntimeError("The Python archive did not contain a working python3.")
    os.chmod(found, 0o755)
    return found


def ensure_voice_venv(runtime_dir: str, python: str) -> str:
    """Create ``hearing/venv`` with pip from the private interpreter."""
    venv = os.path.join(runtime_dir, "hearing", "venv")
    exe = os.path.join(venv, "bin", "python")
    if os.path.isfile(exe) and _python_ok(exe):
        return exe
    os.makedirs(os.path.dirname(venv), exist_ok=True)
    completed = subprocess.run(
        [python, "-m", "venv", venv],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0 or not os.path.isfile(exe):
        detail = (completed.stderr or completed.stdout or "venv failed").strip()[-300:]
        raise RuntimeError(f"Could not create the voice virtualenv. {detail}")
    os.chmod(exe, 0o755)
    probe = subprocess.run(
        [exe, "-m", "pip", "--version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if probe.returncode != 0:
        detail = (probe.stderr or probe.stdout or "pip is missing").strip()[-300:]
        raise RuntimeError(f"The voice virtualenv has no pip. {detail}")
    return exe
