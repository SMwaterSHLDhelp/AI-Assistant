"""The plugin process must start when optional speech packages are not installed."""

import os
import stat
import subprocess
import sys
from pathlib import Path

from ai_assistant.diagnostics import remember, snapshot, write_report


def test_log_ring_keeps_the_last_30_lines_and_the_report_is_private(tmp_path: Path) -> None:
    for index in range(40):
        remember(f"line {index} secret-token")
    lines = snapshot()
    assert len(lines) == 30
    assert lines[0] == "line 10 secret-token"
    assert lines[-1] == "line 39 secret-token"
    path = tmp_path / "Deckling-diagnostics.txt"
    write_report(str(path), lines, "Deckling test")
    assert path.read_text(encoding="utf-8").startswith("Deckling test\n")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_plugin_imports_and_answers_with_optional_deps_banned(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    home = tmp_path / "home" / "deck"
    settings = home / "homebrew" / "settings" / "Deckling"
    runtime = home / "homebrew" / "data" / "Deckling"
    script = r"""
import importlib.machinery
import os
import sys

BANNED = {"openwakeword", "faster_whisper", "numpy", "onnxruntime", "kittentts", "piper"}

class Boom:
    def __init__(self, name):
        self.name = name
    def create_module(self, spec):
        return None
    def exec_module(self, module):
        raise ImportError(f"optional dependency is not installed: {self.name}")

class Ban:
    def find_spec(self, fullname, path, target=None):
        root = fullname.split(".")[0]
        if root not in BANNED:
            return None
        return importlib.machinery.ModuleSpec(fullname, Boom(fullname))

sys.meta_path.insert(0, Ban())

import logging
import types

decky = types.ModuleType("decky")
decky.logger = logging.getLogger("deckling-import")
decky.DECKY_PLUGIN_SETTINGS_DIR = os.environ["DECKLING_SETTINGS"]
decky.DECKY_PLUGIN_RUNTIME_DIR = os.environ["DECKLING_RUNTIME"]

async def emit(event, payload):
    return None

decky.emit = emit
sys.modules["decky"] = decky

import asyncio
import main

plugin = main.Plugin()
asyncio.run(plugin._main())
health = asyncio.run(plugin.health())
assert health["ok"] is True, health
assert health["version"]
plugin.service.hearing.autostart = False
saved = asyncio.run(plugin.save_provider({
    "kind": "llamacpp",
    "name": "llama.cpp on my PC",
    "base_url": "http://127.0.0.1:8080/v1",
    "default_model": "",
}))
assert saved["ok"] is True, saved
heard = asyncio.run(plugin.save_hearing({"wake_enabled": True}))
assert heard["ok"] is True and heard["hearing"]["wake_enabled"] is True, heard
voice = asyncio.run(plugin.save_voice({"voice_enabled": True, "voice_engine": "kittentts"}))
assert voice["ok"] is True and voice["voice"]["voice_engine"] == "kittentts", voice
loaded = set(sys.modules)
missing = BANNED & loaded
assert not missing, missing
print("IMPORT_OK")
"""
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USER"] = "deck"
    env["LOGNAME"] = "deck"
    env["DECKY_USER_HOME"] = str(home)
    env["DECKLING_SETTINGS"] = str(settings)
    env["DECKLING_RUNTIME"] = str(runtime)
    env["PYTHONPATH"] = os.pathsep.join([str(root), str(root / "py_modules")])
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "IMPORT_OK" in result.stdout
