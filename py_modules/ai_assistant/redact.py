"""Redact secrets before they can reach logs or the Quick Access Menu."""

from __future__ import annotations

import logging
import re

# Patterns that should never be written to decky logs or returned raw.
_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-+/=]{8,}"),
    re.compile(r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|authorization)(['\"\s:=]+)[^\s'\",}]+"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"ya29\.[0-9A-Za-z_\-]{10,}"),
)


def redact(value: object) -> str:
    """Return ``value`` as text with credential-shaped substrings removed."""
    text = value if isinstance(value, str) else str(value)
    for pattern in _PATTERNS:
        text = pattern.sub("[redacted]", text)
    return text


def last4(secret: str | None) -> str:
    """A short, non-reversible hint. Empty when the secret is missing or tiny."""
    if not secret or len(secret) < 8:
        return ""
    return secret[-4:]


class RedactFilter(logging.Filter):
    """Defense in depth: scrub log records even if a caller forgets to redact."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact(item) if isinstance(item, str) else item for item in record.args)
        return True
