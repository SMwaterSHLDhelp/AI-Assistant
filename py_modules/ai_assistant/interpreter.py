"""Find a real Python for voice workers.

Decky runs the plugin inside the frozen PluginLoader binary. ``sys.executable``
is that binary, not an interpreter. Launching it runs a second Decky, which
binds the loader port, loads every plugin again, and shuts them down.
"""

from __future__ import annotations

import os
import shutil
import sys

_CANDIDATES = ("python3.13", "python3.11", "python3.12", "python3", "python")


def frozen_runtime() -> bool:
    return bool(getattr(sys, "frozen", False) or getattr(sys, "_MEIPASS", ""))


def system_python() -> str:
    """Return an interpreter that can execute a worker script.

    Outside PluginLoader this is ``sys.executable``. Inside it, this is the
    first system Python that is not the loader binary.
    """
    if not frozen_runtime():
        return sys.executable
    own = os.path.realpath(sys.executable)
    for name in _CANDIDATES:
        found = shutil.which(name)
        if not found:
            continue
        if os.path.realpath(found) == own:
            continue
        if os.access(found, os.X_OK):
            return found
    raise RuntimeError(
        "Voice models need the system Python. "
        f"Decky's PluginLoader cannot run them ({sys.executable})."
    )
