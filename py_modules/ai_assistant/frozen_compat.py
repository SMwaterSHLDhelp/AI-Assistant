"""Load stdlib modules that Decky's PluginLoader binary does not ship.

Decky Loader v3.2.6 is a PyInstaller executable. Its archive has no ``pty``,
``wave``, ``html.parser``, ``_markupbase``, or ``urllib.robotparser``. Those
are imported while ``main.py`` loads, ``sandboxed_plugin.initialize`` catches
the ``ModuleNotFoundError`` and calls ``sys.exit(0)``, and the method socket
never opens. Every frontend call then waits until it times out.

The files under ``_frozen`` are the CPython 3.11.17 standard library (PSF
license, and the robotparser dual notice in that file). They are used only
when this interpreter does not already provide the module.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import traceback
from pathlib import Path

_DIR = Path(__file__).resolve().parent / "_frozen"

# _markupbase is imported by html.parser and is also missing from the archive.
_MODULES: tuple[tuple[str, str], ...] = (
    ("pty", "pty.py"),
    ("wave", "wave.py"),
    ("_markupbase", "_markupbase.py"),
    ("html.parser", "html_parser.py"),
    ("urllib.robotparser", "robotparser.py"),
)


def _missing(name: str) -> bool:
    if name in sys.modules:
        return False
    try:
        return importlib.util.find_spec(name) is None
    except (ImportError, ModuleNotFoundError, ValueError):
        return True


def _load(name: str, filename: str) -> None:
    spec = importlib.util.spec_from_file_location(name, _DIR / filename)
    if spec is None or spec.loader is None:
        raise ImportError(f"Deckling could not load the bundled {name} module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    parent_name, _, child = name.rpartition(".")
    if parent_name:
        parent = importlib.import_module(parent_name)
        setattr(parent, child, module)
    spec.loader.exec_module(module)


def install() -> None:
    """Register any missing modules before the rest of the plugin imports them."""
    try:
        for name, filename in _MODULES:
            if _missing(name):
                _load(name, filename)
    except Exception:
        _write_import_failure(traceback.format_exc())
        raise


def _write_import_failure(detail: str) -> None:
    """The process is about to be killed by the loader. Leave a file the user can open."""
    try:
        from .diagnostics import diagnostics_path, write_report
        from .redact import redact
    except Exception:
        return
    body = redact(detail)
    header = "Deckling failed before the backend could answer.\n" + body.splitlines()[-1]
    paths = [diagnostics_path()]
    import os

    log_dir = os.environ.get("DECKY_PLUGIN_LOG_DIR")
    if log_dir:
        paths.append(os.path.join(log_dir, "boot-error.txt"))
    for path in paths:
        try:
            write_report(path, [body], header)
        except Exception:
            continue
