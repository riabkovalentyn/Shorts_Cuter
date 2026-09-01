"""Pick candidate highlight windows.

Direct port of the Node highlightService: detect scene cuts and silence with
ffmpeg, then score fixed-length windows by audio activity plus scene density
and greedily take the best non-overlapping ones.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from app.services import media

log = logging.getLogger(__name__)

_PTS_TIME = re.compile(r"pts_time:([0-9]+\.[0-9]+)")
_SILENCE_START = re.compile(r"silence_start: (-?[0-9]+\.?[0-9]*)")
_SILENCE_END = re.compile(r"silence_end: ([0-9]+\.?[0-9]*)")

SCENE_THRESHOLD = 0.35
SCENE_WEIGHT = 0.75


@dataclass
class HighlightWindow:
    start: float
    duration: float
    score: float


async def _detect_scenes(path: Path, threshold: float = SCENE_THRESHOLD) -> list[float]:
    _, stderr = await media.run(
        media.ffmpeg_path(),
        [
            "-i",
            str(path),
            "-filter:v",
            "select='gt(scene," + str(threshold) + ")',showinfo",
            "-f",
            "null",
            "-",
        ],
    )
    return [float(m) for m in _PTS_TIME.findall(stderr)]


async def _detect_silence(path: Path) -> list[tuple[float, float]]:
    _, stderr = await media.run(
        media.ffmpeg_path(),
        [
            "-i",
            str(path),
            "-af",
            "silencedetect=noise=-30dB:d=0.5",
            "-f",
            "null",
            "-",
        ],
    )
    starts = [float(m) for m in _SILENCE_START.findall(stderr)]
    ends = [float(m) for m in _SILENCE_END.findall(stderr)]
    return list(zip(starts, ends))


def _activity_intervals(
    silences: list[tuple[float, float]], duration: float
) -> list[tuple[float, float]]:
    """Complement of the silent ranges."""
    activity: list[tuple[float, float]] = []
    cursor = 0.0
    for raw_start, raw_end in silences:
        start = max(0.0, raw_start)
        end = min(duration, raw_end)
        if start > cursor:
            activity.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < duration:
        activity.append((cursor, duration))
    return activity


def _overlaps(a: HighlightWindow, b: HighlightWindow) -> bool:
    return not (
        a.start + a.duration <= b.start or b.start + b.duration <= a.start
    )


async def detect_highlights(
    path: Path, clip_length_sec: float, max_clips: int = 5
) -> list[HighlightWindow]:
    clip_len = max(5.0, float(clip_length_sec))
    limit = max(1, int(max_clips))

    duration = await media.probe_duration(path)
    if not duration or duration < 1:
        return []

    scenes, silences = await asyncio.gather(
        _detect_scenes(path), _detect_silence(path)
    )
    activity = _activity_intervals(silences, duration)
    log.info(
        "[highlight] duration=%.1fs scenes=%d silences=%d",
        duration,
        len(scenes),
        len(silences),
    )

    def window_score(start: float) -> float:
        end = min(duration, start + clip_len)
        active = 0.0
        for a_start, a_end in activity:
            overlap = min(end, a_end) - max(start, a_start)
            if overlap > 0:
                active += overlap
        scene_count = sum(1 for t in scenes if start <= t < end)
        return active + scene_count * SCENE_WEIGHT

    candidates = sorted({0.0, *scenes})
    candidates = [t for t in candidates if t < duration - 0.5]

    scored = sorted(
        (
            HighlightWindow(
                start=t, duration=min(clip_len, duration - t), score=window_score(t)
            )
            for t in candidates
        ),
        key=lambda w: w.score,
        reverse=True,
    )

    picked: list[HighlightWindow] = []
    for window in scored:
        if len(picked) >= limit:
            break
        if any(_overlaps(window, chosen) for chosen in picked):
            continue
        picked.append(window)

    # Fallback: evenly spaced windows when scoring produced nothing usable.
    if not picked:
        count = min(limit, max(1, int(duration // clip_len)))
        for i in range(count):
            start = i * clip_len
            if start >= duration - 0.5:
                break
            picked.append(
                HighlightWindow(
                    start=start, duration=min(clip_len, duration - start), score=0.0
                )
            )

    picked.sort(key=lambda w: w.start)
    return picked
