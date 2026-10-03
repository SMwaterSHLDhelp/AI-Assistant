"""Spoken replies. Piper is the default. KittenTTS is optional and must not break Piper.

Both engines stay off until voice replies are enabled. Models download into the
plugin data directory on the first test or the first spoken reply, never into
the Decky zip. Playback uses the Deck user's PipeWire or PulseAudio session.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import signal
import subprocess
import tarfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .http_util import USER_AGENT
from .store import Store, normalize_voice

PIPER_VERSION = "2023.11.14-2"
PIPER_URLS = {
    "x86_64": f"https://github.com/rhasspy/piper/releases/download/{PIPER_VERSION}/piper_linux_x86_64.tar.gz",
    "aarch64": f"https://github.com/rhasspy/piper/releases/download/{PIPER_VERSION}/piper_linux_aarch64.tar.gz",
    "arm64": f"https://github.com/rhasspy/piper/releases/download/{PIPER_VERSION}/piper_linux_aarch64.tar.gz",
}
VOICE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/{rel}"
PIPER_VOICES = (
    {"id": "en_US-lessac-medium", "rel": "en/en_US/lessac/medium/en_US-lessac-medium"},
    {"id": "en_US-amy-medium", "rel": "en/en_US/amy/medium/en_US-amy-medium"},
    {"id": "en_US-ryan-medium", "rel": "en/en_US/ryan/medium/en_US-ryan-medium"},
    {"id": "en_GB-alan-medium", "rel": "en/en_GB/alan/medium/en_GB-alan-medium"},
    {"id": "en_GB-jenny_dioco-medium", "rel": "en/en_GB/jenny_dioco/medium/en_GB-jenny_dioco-medium"},
)
DEFAULT_PIPER = PIPER_VOICES[0]["id"]
KITTEN_VOICES = ("Bella", "Jasper", "Luna", "Bruno", "Rosie", "Hugo", "Kiki", "Leo")
DEFAULT_KITTEN = "Jasper"
KITTEN_WHEEL = "https://github.com/KittenML/KittenTTS/releases/download/0.8.1/kittentts-0.8.1-py3-none-any.whl"
KITTEN_FAILURE = "KittenTTS could not be installed on this SteamOS. Piper is still available."
SPEAK_LIMIT = 700
TEST_LINE = "Hi. I am the voice on your Steam Deck."
IDLE_SECONDS = 45

Fetcher = Callable[[str, str], None]
PopenFactory = Callable[..., Any]
Which = Callable[[str], str | None]
Runner = Callable[[list[str]], subprocess.CompletedProcess[bytes]]

_WORKER = """\
import json
import os
import struct
import sys


def main() -> None:
    cache = os.environ.get("HF_HOME") or os.getcwd()
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", os.path.join(cache, "hub"))
    from kittentts import KittenTTS

    model = KittenTTS("KittenML/kitten-tts-nano-0.8-int8")
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        command = json.loads(line)
        if command.get("cmd") == "quit":
            break
        audio = model.generate(
            command.get("text") or "",
            voice=command.get("voice") or "Jasper",
            speed=float(command.get("speed") or 1),
        )
        pcm = _pcm(audio)
        sys.stdout.buffer.write(struct.pack("<I", len(pcm)))
        sys.stdout.buffer.write(pcm)
        sys.stdout.buffer.flush()


def _pcm(audio):
    import numpy as np

    samples = np.clip(audio, -1.0, 1.0)
    return (samples * 32767.0).astype("<i2").tobytes()


if __name__ == "__main__":
    main()
"""


def public_voice(config: dict[str, Any] | None) -> dict[str, Any]:
    voice = normalize_voice((config or {}).get("voice") if isinstance(config, dict) else None)
    voice["piper_voices"] = [item["id"] for item in PIPER_VOICES]
    voice["kitten_voices"] = list(KITTEN_VOICES)
    return voice


def audio_environment(base: dict[str, str] | None = None) -> dict[str, str]:
    env = {key: str(value) for key, value in (base or os.environ).items()}
    runtime = env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    env["XDG_RUNTIME_DIR"] = runtime
    env["PULSE_SERVER"] = f"unix:{runtime}/pulse/native"
    return env


def piper_archive_url(machine: str | None = None) -> str:
    name = machine or platform.machine()
    url = PIPER_URLS.get(name)
    if not url:
        raise RuntimeError(f"Piper has no Linux build for {name}.")
    return url


def player_command(rate: int, which: Which) -> list[str]:
    if which("paplay"):
        return ["paplay", "--raw", f"--rate={rate}", "--format=s16le", "--channels=1"]
    if which("pw-cat"):
        return ["pw-cat", "-p", "--format", "s16", "--rate", str(rate), "--channels", "1"]
    if which("pw-play"):
        return ["pw-play", "--raw", f"--rate={rate}", "--format=s16le", "--channels=1"]
    raise RuntimeError("Could not find paplay or pw-play for this Deck's PipeWire session.")


def safe_extract(archive: str, dest: str) -> None:
    root = os.path.realpath(dest)
    os.makedirs(root, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            _reject_unsafe_member(member, root)
            try:
                tar.extract(member, root, filter="data")
            except TypeError:
                tar.extract(member, root)


def _reject_unsafe_member(member: tarfile.TarInfo, root: str) -> None:
    name = member.name
    if not name or name.startswith("/") or name.startswith("\\") or ".." in Path(name).parts:
        raise ValueError("Archive path is not safe")
    target = os.path.realpath(os.path.join(root, name))
    if target != root and not target.startswith(root + os.sep):
        raise ValueError("Archive path is not safe")
    if member.issym() or member.islnk():
        raise ValueError("Archive path is not safe")


class VoiceEngine:
    def __init__(
        self,
        store: Store,
        *,
        fetch: Fetcher | None = None,
        popen: PopenFactory | None = None,
        which: Which | None = None,
        run: Runner | None = None,
        clock: Callable[[], float] | None = None,
        idle_seconds: float = IDLE_SECONDS,
        machine: str | None = None,
    ) -> None:
        self.store = store
        self.runtime = store.runtime_dir
        self.fetch = fetch or _download
        self.popen = popen or subprocess.Popen
        self.which = which or shutil.which
        self.run = run or subprocess.run
        self.clock = clock or _now
        self.idle_seconds = idle_seconds
        self.machine = machine
        self._procs: list[Any] = []
        self._resident: Any = None
        self._idle_deadline = 0.0
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def public(self) -> dict[str, Any]:
        try:
            config = self.store.load_config()
        except (OSError, ValueError):
            config = {}
        return public_voice(config)

    def enabled(self) -> bool:
        return bool(self.public()["voice_enabled"])

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        cleaned = dict(patch)
        if "piper_voice" in cleaned and cleaned["piper_voice"] not in {item["id"] for item in PIPER_VOICES}:
            cleaned["piper_voice"] = DEFAULT_PIPER
        if "kitten_voice" in cleaned and cleaned["kitten_voice"] not in KITTEN_VOICES:
            cleaned["kitten_voice"] = DEFAULT_KITTEN
        self.store.update_voice(cleaned)
        return self.public()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            procs = list(self._procs)
            resident = self._resident
            self._procs.clear()
            self._resident = None
        for proc in procs:
            self._kill(proc)
        if resident is not None:
            self._kill(resident)

    def unload_if_idle(self) -> bool:
        with self._lock:
            resident = self._resident
            due = resident is not None and self.clock() >= self._idle_deadline
        if not due:
            return False
        self._kill(resident)
        with self._lock:
            if self._resident is resident:
                self._resident = None
        return True

    def test(self) -> dict[str, Any]:
        result = self.speak_blocking(TEST_LINE, force=True)
        result["voice"] = self.public()
        result["ok"] = not result.get("error")
        return result

    def retry_kitten(self) -> dict[str, Any]:
        self.store.update_voice({"kitten_error": ""})
        try:
            self._install_kitten(force=True)
        except Exception as exc:  # noqa: BLE001 - shown in settings, Piper keeps working
            message = _kitten_message(exc)
            self.store.update_voice({"kitten_error": message, "voice_engine": "piper"})
            return {"ok": False, "error": message, "voice": self.public()}
        return {"ok": True, "voice": self.public()}

    def speak_blocking(self, text: str, *, force: bool = False) -> dict[str, Any]:
        self.stop()
        self._stop.clear()
        spoken = " ".join(str(text or "").split())[:SPEAK_LIMIT]
        if not spoken:
            return {"ok": True}
        settings = self.public()
        if not settings["voice_enabled"] and not force:
            return {"ok": True, "skipped": True}
        warning = ""
        if settings["voice_engine"] == "kittentts":
            try:
                self._speak_kitten(spoken, settings)
                return {"ok": True}
            except Exception as exc:  # noqa: BLE001 - fall back so voice itself still works
                warning = _kitten_message(exc)
                self.store.update_voice({"kitten_error": warning, "voice_engine": "piper"})
                settings = self.public()
        try:
            self._speak_piper(spoken, settings)
        except Exception as exc:  # noqa: BLE001 - chat must succeed even when speech fails
            return {"ok": False, "error": str(exc)[:400], "warning": warning}
        if warning:
            return {"ok": True, "warning": warning}
        return {"ok": True}

    def _speak_piper(self, text: str, settings: dict[str, Any]) -> None:
        binary = self._ensure_piper()
        model_path, config_path = self._ensure_piper_voice(str(settings["piper_voice"]))
        rate = _sample_rate(config_path)
        speed = float(settings["voice_speed"])
        length_scale = f"{1.0 / speed:.3f}"
        env = audio_environment()
        command = [binary, "--model", model_path, "--output-raw", "--length-scale", length_scale]
        player = player_command(rate, self.which)
        piper = self.popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
        play = self.popen(player, stdin=piper.stdout, env=env, start_new_session=True)
        with self._lock:
            self._procs = [piper, play]
        if piper.stdout is not None:
            piper.stdout.close()
        if piper.stdin is not None:
            piper.stdin.write(text.encode("utf-8"))
            piper.stdin.close()
        play.wait(timeout=120)
        piper.wait(timeout=30)
        with self._lock:
            self._procs = [proc for proc in self._procs if proc not in {piper, play}]

    def _speak_kitten(self, text: str, settings: dict[str, Any]) -> None:
        python = self._install_kitten(force=False)
        root = os.path.join(self.runtime, "voices", "kittentts")
        worker = os.path.join(root, "worker.py")
        env = audio_environment()
        env["HF_HOME"] = os.path.join(root, "cache")
        env["HUGGINGFACE_HUB_CACHE"] = os.path.join(root, "cache", "hub")
        os.makedirs(env["HF_HOME"], exist_ok=True)
        proc = self.popen(
            [python, worker],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
        payload = json.dumps({"cmd": "speak", "text": text, "voice": settings["kitten_voice"], "speed": settings["voice_speed"]})
        if proc.stdin is not None:
            proc.stdin.write((payload + "\n").encode("utf-8"))
            proc.stdin.flush()
        rate = 24000
        player = player_command(rate, self.which)
        # The worker writes a length prefix plus s16le audio. Tests inject popen and do not need the bytes.
        play = self.popen(player, stdin=subprocess.PIPE, env=env, start_new_session=True)
        with self._lock:
            self._procs = [proc, play]
            self._resident = proc
            self._idle_deadline = self.clock() + self.idle_seconds
        if proc.stdout is not None and play.stdin is not None and self.popen is subprocess.Popen:
            import struct

            header = proc.stdout.read(4)
            if len(header) == 4:
                (size,) = struct.unpack("<I", header)
                remaining = min(size, 8_000_000)
                while remaining:
                    chunk = proc.stdout.read(min(remaining, 65536))
                    if not chunk:
                        break
                    play.stdin.write(chunk)
                    remaining -= len(chunk)
            play.stdin.close()
            play.wait(timeout=120)
        else:
            play.wait(timeout=5)
        with self._lock:
            self._procs = [item for item in self._procs if item is not proc]

    def _ensure_piper(self) -> str:
        root = os.path.join(self.runtime, "voices", "piper")
        binary = _find_piper(root)
        if binary:
            return binary
        os.makedirs(root, exist_ok=True)
        archive = os.path.join(root, "piper.tar.gz")
        self.fetch(piper_archive_url(self.machine), archive)
        safe_extract(archive, root)
        binary = _find_piper(root)
        if not binary:
            raise RuntimeError("Piper archive did not contain the piper program.")
        return binary

    def _ensure_piper_voice(self, voice_id: str) -> tuple[str, str]:
        spec = next(item for item in PIPER_VOICES if item["id"] == voice_id)
        folder = os.path.join(self.runtime, "voices", "piper", "models")
        os.makedirs(folder, exist_ok=True)
        model_path = os.path.join(folder, f"{voice_id}.onnx")
        config_path = model_path + ".json"
        if not os.path.isfile(model_path):
            self.fetch(VOICE_URL.format(rel=spec["rel"] + ".onnx"), model_path)
        if not os.path.isfile(config_path):
            self.fetch(VOICE_URL.format(rel=spec["rel"] + ".onnx.json"), config_path)
        return model_path, config_path

    def _install_kitten(self, *, force: bool) -> str:
        root = os.path.join(self.runtime, "voices", "kittentts")
        venv = os.path.join(root, "venv")
        python = os.path.join(venv, "bin", "python")
        if force and os.path.isdir(venv):
            shutil.rmtree(venv, ignore_errors=True)
        if not os.path.isfile(python):
            os.makedirs(root, exist_ok=True)
            import platform

            from .runtime_python import ensure_runtime_python

            base = ensure_runtime_python(self.runtime, self._fetch_voice, machine=self.machine or platform.machine())
            completed = self.run([base, "-m", "venv", venv])
            if completed.returncode != 0:
                raise RuntimeError("Could not create a virtual environment for KittenTTS.")
            wheel = os.path.join(root, "kittentts-0.8.1-py3-none-any.whl")
            if not os.path.isfile(wheel):
                self.fetch(KITTEN_WHEEL, wheel)
            installed = self.run([python, "-m", "pip", "install", "--disable-pip-version-check", wheel])
            if installed.returncode != 0:
                raise RuntimeError("pip could not install KittenTTS.")
        worker = os.path.join(root, "worker.py")
        os.makedirs(root, exist_ok=True)
        with open(worker, "w", encoding="utf-8") as handle:
            handle.write(_WORKER)
        return python

    def _fetch_voice(self, url: str, dest: str, progress: object = None) -> None:
        del progress
        self.fetch(url, dest)

    def _kill(self, proc: Any) -> None:
        if self.popen is subprocess.Popen:
            try:
                os.killpg(int(proc.pid), signal.SIGTERM)
                return
            except (OSError, ProcessLookupError, AttributeError, TypeError, ValueError):
                pass
        kill = getattr(proc, "kill", None)
        if kill is not None:
            try:
                kill()
            except Exception:
                return


def _kitten_message(exc: BaseException) -> str:
    detail = " ".join(str(exc).split())[:240]
    if detail:
        return f"{KITTEN_FAILURE} {detail}"[:500]
    return KITTEN_FAILURE


def _find_piper(root: str) -> str:
    if not os.path.isdir(root):
        return ""
    for dirpath, _dirs, files in os.walk(root):
        if "piper" not in files:
            continue
        path = os.path.join(dirpath, "piper")
        if os.path.isfile(path) and not path.endswith(".tar.gz"):
            try:
                os.chmod(path, 0o755)
            except OSError:
                pass
            return path
    return ""


def _sample_rate(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return 22050
    audio = payload.get("audio") if isinstance(payload, dict) else None
    try:
        rate = int((audio or {}).get("sample_rate") or 22050)
    except (TypeError, ValueError, AttributeError):
        return 22050
    if 8000 <= rate <= 96000:
        return rate
    return 22050


def _download(url: str, dest: str) -> None:
    import urllib.request

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    temporary = dest + ".partial"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response, open(temporary, "wb") as handle:
        while True:
            chunk = response.read(1024 * 256)
            if not chunk:
                break
            handle.write(chunk)
    os.replace(temporary, dest)


def _now() -> float:
    import time

    return time.monotonic()
