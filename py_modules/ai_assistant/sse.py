"""Parsers for server-sent events and newline-delimited JSON streams."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any


def iter_sse_json(lines: Iterator[str]) -> Iterator[Any]:
    """Yield JSON objects from ``data:`` fields. ``[DONE]`` ends the stream."""
    data_lines: list[str] = []

    def _flush() -> Any | None:
        nonlocal data_lines
        if not data_lines:
            return None
        raw = "\n".join(data_lines).strip()
        data_lines = []
        if not raw or raw == "[DONE]":
            return raw
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    for line in lines:
        if line == "":
            item = _flush()
            if item == "[DONE]":
                return
            if item is not None and item != "":
                yield item
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    item = _flush()
    if isinstance(item, (dict, list)):
        yield item


def iter_json_lines(lines: Iterator[str]) -> Iterator[Any]:
    """Yield JSON objects from a newline-delimited body (Ollama)."""
    for line in lines:
        raw = line.strip()
        if not raw:
            continue
        try:
            yield json.loads(raw)
        except json.JSONDecodeError:
            continue
