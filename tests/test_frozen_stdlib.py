"""Decky's PluginLoader does not ship every stdlib module the plugin imports."""

import os
import subprocess
import sys
from pathlib import Path


def test_real_stdlib_is_left_alone() -> None:
    import pty
    import wave

    from ai_assistant.frozen_compat import install

    install()
    assert "lib/python" in pty.__file__
    assert "lib/python" in wave.__file__


def test_missing_loader_modules_still_let_the_plugin_answer(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    home = tmp_path / "home" / "deck"
    settings = home / "homebrew" / "settings" / "Deckling"
    runtime = home / "homebrew" / "data" / "Deckling"
    script = r"""
import os
import sys

BANNED = {
    "pty", "wave", "html.parser", "_markupbase", "urllib.robotparser",
    "http.server", "socketserver", "glob", "tty",
}

class Ban:
    def find_spec(self, fullname, path, target=None):
        if fullname not in BANNED:
            return None
        raise ModuleNotFoundError(f"No module named {fullname!r}")

sys.meta_path.insert(0, Ban())

import logging
import types

decky = types.ModuleType("decky")
decky.logger = logging.getLogger("deckling-frozen")
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
saved = asyncio.run(plugin.save_provider({
    "kind": "llamacpp",
    "name": "llama.cpp on my PC",
    "base_url": "http://127.0.0.1:8080/v1",
    "default_model": "",
}))
assert saved["ok"] is True, saved

from pathlib import Path
wav = Path(os.environ["DECKLING_RUNTIME"]) / "tone.wav"
from ai_assistant.hearing import write_wav
write_wav(str(wav), b"\x00\x00" * 8, rate=8000)
assert wav.stat().st_size > 44

from html.parser import HTMLParser
from ai_assistant.web import extract_text
title, text = extract_text("<html><title>Grace</title><p>north</p></html>")
assert title == "Grace" and "north" in text

import urllib.robotparser
parser = urllib.robotparser.RobotFileParser()
parser.parse(["User-agent: *", "Disallow: /"])
assert parser.can_fetch("Deckling", "https://example.com/") is False
print("FROZEN_OK")
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
    assert "FROZEN_OK" in result.stdout


def test_ui_names_a_dead_backend_and_the_log_path() -> None:
    root = Path(__file__).resolve().parents[1]
    api = (root / "src" / "api.ts").read_text(encoding="utf-8")
    assert 'BACKEND_DOWN = "Backend not responding."' in api
    assert "~/homebrew/logs/Deckling/boot-error.txt" in api
    assert "journalctl -u plugin_loader" in api
    page = (root / "src" / "settings" / "SettingsPage.tsx").read_text(encoding="utf-8")
    assert "backendUnreachable" in page
    assert "Hide details" in page
    assert ".slice(0, 15)" in page


def test_an_import_failure_still_answers_health_with_the_traceback(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    home = tmp_path / "home"
    settings = home / "settings"
    runtime = home / "runtime"
    script = r"""
import os
import sys

BANNED = {"secrets"}

class Ban:
    def find_spec(self, fullname, path, target=None):
        if fullname not in BANNED:
            return None
        raise ModuleNotFoundError(f"No module named {fullname!r}")

sys.meta_path.insert(0, Ban())

import logging
import types

decky = types.ModuleType("decky")
decky.logger = logging.getLogger("deckling-boot")
decky.DECKY_PLUGIN_SETTINGS_DIR = os.environ["DECKLING_SETTINGS"]
decky.DECKY_PLUGIN_RUNTIME_DIR = os.environ["DECKLING_RUNTIME"]

async def emit(event, payload):
    return None

decky.emit = emit
sys.modules["decky"] = decky

import asyncio
import main

plugin = main.Plugin()
asyncio.run(plugin._migration())
asyncio.run(plugin._main())
health = asyncio.run(plugin.health())
assert health["ok"] is False, health
assert "secrets" in health["error"]
assert "Traceback" in health["traceback"]
assert "secrets" in health["traceback"]
boot = os.path.join(os.environ["DECKY_PLUGIN_LOG_DIR"], "boot-error.txt")
text = open(boot, encoding="utf-8").read()
assert "secrets" in text and "Traceback" in text
print("BOOT_OK")
"""
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["DECKY_USER_HOME"] = str(home)
    env["DECKY_PLUGIN_LOG_DIR"] = str(home / "logs")
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
    assert "BOOT_OK" in result.stdout
