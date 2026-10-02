#!/usr/bin/env python3
"""Compatibility entry point. The implementation lives in deckling_bridge.py.

Existing commands that run ``python3 bridge/claude_bridge.py`` keep working.
This file does not start a server until it is executed as a program.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).with_name("deckling_bridge.py")
_SPEC = importlib.util.spec_from_file_location("deckling_bridge", _PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("deckling_bridge.py is missing")
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("deckling_bridge", _MODULE)
_SPEC.loader.exec_module(_MODULE)

find_claude = _MODULE.find_claude
claude_command = _MODULE.claude_command
child_env = _MODULE.child_env
_authorized = _MODULE._authorized
make_handler = _MODULE.make_handler
serve = _MODULE.serve
main = _MODULE.main

if __name__ == "__main__":
    main()
