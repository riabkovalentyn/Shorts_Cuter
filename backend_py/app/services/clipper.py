"""Cut clips + thumbnails with ffmpeg and persist Clip documents."""

import logging
from pathlib import Path

from beanie import PydanticObjectId

from app.config import get_settings
from app.models import Clip
from app.services import media
from app.services.highlight import HighlightWindow

log = logging.getLogger(__name__)

# ffmpeg complains this way when a seek lands past the last keyframe; the
# segment is unusable but the rest of the job is fine, so we skip it.
_SKIPPABLE = ("does not contain any stream", "Invalid argument")

_ENCODE_ARGS = [
    "-c:v",
    "libx264",
    "-preset",
    "veryfast",
    "-crf",
    "23",
    "-c:a",
    "aac",
    "-b:a",
    "128k",
    "-movflags",
    "+faststart",
]


def _is_skippable(message: str) -> bool:
    return any(needle.lower() in message.lower() for needle in _SKIPPABLE)


async def _cut(source: Path, target: Path, start: float, duration: float) -> None:
    await media.run_checked(
        media.ffmpeg_path(),
        [
            "-y",
            "-ss",
            format(start, ".3f"),
            "-i",
            str(source),
            "-t",
            format(duration, ".3f"),
            *_ENCODE_ARGS,
            str(target),
        ],
    )


async def _thumbnail(clip_path: Path, target: Path, duration: float) -> None:
    at = max(0.5, min(1.0, duration / 2))
    await media.run_checked(
        media.ffmpeg_path(),
        [
            "-y",
            "-ss",
            format(at, ".3f"),
            "-i",
            str(clip_path),
            "-frames:v",
            "1",
            str(target),
        ],
    )


async def slice_windows(
    source: Path, windows: list[HighlightWindow], job_id: str
) -> list[Clip]:
    """Cut the given windows out of `source`, one Clip document per window."""
    settings = get_settings()
    settings.clips_dir.mkdir(parents=True, exist_ok=True)
    object_id = PydanticObjectId(job_id)

    clips: list[Clip] = []
    for index, window in enumerate(windows):
        if window.duration < 0.5:
            continue

        base = str(job_id) + "_" + str(index)
        clip_path = settings.clips_dir / (base + ".mp4")
        thumb_path = settings.clips_dir / (base + ".jpg")

        try:
            await _cut(source, clip_path, window.start, window.duration)
        except media.FFmpegError as exc:
            if _is_skippable(str(exc)):
                log.warning("[clipper] skipping window %d: %s", index, exc)
                continue
            raise

        try:
            await _thumbnail(clip_path, thumb_path, window.duration)
            thumb: str | None = str(thumb_path)
        except media.FFmpegError as exc:
            # A missing thumbnail should not fail the whole job.
            log.warning("[clipper] thumbnail failed for window %d: %s", index, exc)
            thumb = None

        clip = Clip(
            jobId=object_id,
            index=index,
            startSec=window.start,
            durationSec=window.duration,
            score=window.score,
            filePath=str(clip_path),
            thumbPath=thumb,
            title="Clip " + str(index + 1),
            description="Auto-generated clip " + str(index + 1),
            hashtags=["#Shorts", "#stream"],
        )
        await clip.insert()
        clips.append(clip)

    log.info("[clipper] produced %d clip(s) for job %s", len(clips), job_id)
    return clips


async def slice_fixed(source: Path, clip_length_sec: float, job_id: str) -> list[Clip]:
    """Fallback: cut the whole video into fixed-length consecutive clips."""
    media.ensure_binaries()
    clip_length = max(5.0, float(clip_length_sec))

    duration = await media.probe_duration(source)
    if not duration or duration < 1:
        raise media.FFmpegError(
            "Input video duration is 0. Check the download step or the source URL."
        )

    windows: list[HighlightWindow] = []
    count = max(1, int(-(-duration // clip_length)))  # ceil
    for i in range(count):
        start = i * clip_length
        if start > duration - 0.5:
            break
        span = min(clip_length, duration - start)
        if span < 0.5:
            continue
        windows.append(HighlightWindow(start=start, duration=span, score=0.0))

    return await slice_windows(source, windows, job_id)
