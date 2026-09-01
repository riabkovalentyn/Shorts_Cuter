"""Pick candidate highlight windows.

Detects scene cuts and silence with ffmpeg, then scores fixed-length windows by
audio activity plus scene density and greedily takes the best non-overlapping
ones.

The scoring formula is unchanged from the original Node implementation. What
changed is which windows get scored: candidates used to be *only* the scene-cut
timestamps, which meant a static talk stream had almost none and most of the
VOD could never be clipped at all.
"""

import asyncio
import logging
import re
from bisect import bisect_left, bisect_right
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.services import media

log = logging.getLogger(__name__)

_PTS_TIME = re.compile(r"pts_time:([0-9]+\.[0-9]+)")
_SILENCE_START = re.compile(r"silence_start: (-?[0-9]+\.?[0-9]*)")
_SILENCE_END = re.compile(r"silence_end: ([0-9]+\.?[0-9]*)")

SCENE_THRESHOLD = 0.35
SCENE_WEIGHT = 0.75

# Shortest clip worth cutting; also the smallest tail we will keep at the very
# end of a video. Matches Twitch's own 5s minimum clip length.
MIN_CLIP_SEC = 5.0


@dataclass
class HighlightWindow:
    start: float
    duration: float
    score: float
    # Populated by the AI selector; the heuristic path leaves these unset and
    # metadataService fills in templated text instead.
    title: str | None = None
    description: str | None = None
    reason: str | None = None


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
        timeout=get_settings().analysis_timeout_sec,
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
        timeout=get_settings().analysis_timeout_sec,
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


def _active_before(activity: list[tuple[float, float]]) -> Callable[[float], float]:
    """Build an O(log n) lookup for 'active seconds before t'.

    Candidate counts grow with VOD length, so summing every interval per window
    would make a long stream quadratic.
    """
    starts = [s for s, _ in activity]
    ends = [e for _, e in activity]
    prefix: list[float] = []
    total = 0.0
    for start, end in activity:
        prefix.append(total)
        total += end - start

    def lookup(t: float) -> float:
        index = bisect_right(starts, t) - 1
        if index < 0:
            return 0.0
        return prefix[index] + max(0.0, min(t, ends[index]) - starts[index])

    return lookup


def _overlaps(a: HighlightWindow, b: HighlightWindow) -> bool:
    return not (
        a.start + a.duration <= b.start or b.start + b.duration <= a.start
    )


def _candidate_starts(
    scenes: list[float], duration: float, clip_len: float
) -> list[float]:
    """Scene cuts plus a regular stride, so no stretch is unreachable."""
    stride = max(1.0, clip_len / 2)
    grid = [i * stride for i in range(int(duration / stride) + 1)]
    latest = duration - min(MIN_CLIP_SEC, clip_len)
    return sorted({t for t in (0.0, *scenes, *grid) if 0.0 <= t <= latest})


async def detect_highlights(
    path: Path, clip_length_sec: float, max_clips: int = 5
) -> list[HighlightWindow]:
    clip_len = max(MIN_CLIP_SEC, float(clip_length_sec))
    limit = max(1, int(max_clips))

    duration = await media.probe_duration(path)
    if not duration or duration < 1:
        return []

    scenes, silences = await asyncio.gather(
        _detect_scenes(path), _detect_silence(path)
    )
    scenes.sort()
    activity = _activity_intervals(silences, duration)
    active_before = _active_before(activity)

    candidates = _candidate_starts(scenes, duration, clip_len)
    log.info(
        "[highlight] duration=%.1fs scenes=%d silences=%d candidates=%d",
        duration,
        len(scenes),
        len(silences),
        len(candidates),
    )
    if not candidates:
        return []

    def window_score(start: float) -> float:
        end = min(duration, start + clip_len)
        active = active_before(end) - active_before(start)
        scene_count = bisect_left(scenes, end) - bisect_left(scenes, start)
        return active + scene_count * SCENE_WEIGHT

    # Stable sort: equal scores keep ascending-time order, so results are
    # deterministic rather than dependent on set iteration order.
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

    picked.sort(key=lambda w: w.start)
    return picked
