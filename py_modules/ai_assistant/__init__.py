"""Deckling backend package. Imported by main.py from Decky's py_modules path."""

from .frozen_compat import install

# Before service.py imports pty, wave, and html.parser. Decky's frozen
# interpreter does not ship those, and a failed import exits the process.
install()

__version__ = "0.1.0"
