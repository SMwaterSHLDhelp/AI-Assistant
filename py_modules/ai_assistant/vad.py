"""Energy voice-activity detection. No extra packages, so tests and SteamOS can both use it."""

from __future__ import annotations

import array

RATE = 16000
FRAME_MS = 30
THRESHOLD = 400.0
SILENCE_MS = 700
MIN_SPEECH_MS = 200
MAX_MS = 15000
NO_SPEECH_MS = 4000


def frame_bytes() -> int:
    return RATE * FRAME_MS // 1000 * 2


def rms(frame: bytes) -> float:
    usable = frame[: len(frame) - (len(frame) % 2)]
    if not usable:
        return 0.0
    samples = array.array("h")
    samples.frombytes(usable)
    if not samples:
        return 0.0
    total = sum(sample * sample for sample in samples)
    return (total / len(samples)) ** 0.5


def speech_region(
    pcm: bytes,
    *,
    threshold: float = THRESHOLD,
    silence_ms: int = SILENCE_MS,
    min_speech_ms: int = MIN_SPEECH_MS,
    frame_ms: int = FRAME_MS,
) -> tuple[int, int] | None:
    """Return ``(start, end)`` byte offsets when speech has finished, or None while it is still open."""
    width = RATE * frame_ms // 1000 * 2
    if width <= 0:
        return None
    silence_needed = max(1, silence_ms // frame_ms)
    speech_needed = max(1, min_speech_ms // frame_ms)
    speech_frames = 0
    silence_frames = 0
    start: int | None = None
    for index in range(0, len(pcm) - width + 1, width):
        loud = rms(pcm[index : index + width]) >= threshold
        if loud:
            if start is None:
                start = index
            speech_frames += 1
            silence_frames = 0
            continue
        if start is None:
            continue
        silence_frames += 1
        if speech_frames >= speech_needed and silence_frames >= silence_needed:
            end = index + width
            return start, end
    return None
