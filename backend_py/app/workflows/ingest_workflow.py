"""The end-to-end pipeline: download -> detect highlights -> cut -> metadata."""

import asyncio
import contextlib
import logging
from pathlib import Path

from app.config import get_settings
from app.models import Job
from app.services import ai_highlights, clipper, highlight, ingest, media, metadata
from app.services.ai_highlights import AIUnavailable
from app.services.highlight import HighlightWindow
from app.services.transcribe import TranscriptionUnavailable, transcribe

log = logging.getLogger(__name__)

# Keep strong references so in-process tasks are not garbage collected midway.
_background_tasks: set[asyncio.Task] = set()


def _discard_source(source: Path | None) -> None:
    """Delete the downloaded VOD once clips exist.

    A 4h Twitch VOD is several GB and nothing reads it after clipping, so
    leaving it behind fills the disk one job at a time.
    """
    if source is None or get_settings().keep_source_video:
        return
    with contextlib.suppress(OSError):
        if source.exists():
            size_mb = source.stat().st_size / (1024 * 1024)
            source.unlink()
            log.info("[pipeline] removed source %s (%.0f MB)", source.name, size_mb)


async def _select_windows(
    source: Path, clip_length_sec: float
) -> tuple[list[HighlightWindow], bool]:
    """Pick clip windows. Returns (windows, came_from_ai).

    The AI path transcribes the VOD and asks Claude which moments a viewer
    would clip. If it is unavailable for any reason - no API key, no
    faster-whisper, a refusal, a malformed response - we fall back to the
    scene/silence scorer rather than failing the job.
    """
    settings = get_settings()

    if settings.ai_enabled:
        try:
            duration = await media.probe_duration(source)
            segments = await transcribe(source)
            windows = await ai_highlights.select_highlights(
                segments, duration, settings.max_clips
            )
            if windows:
                return windows, True
            log.warning("[pipeline] AI found no clip-worthy moments; using heuristic")
        except (AIUnavailable, TranscriptionUnavailable) as exc:
            log.warning("[pipeline] AI selection unavailable (%s); using heuristic", exc)
        except Exception:  # noqa: BLE001 - never let selection sink the job
            log.exception("[pipeline] AI selection failed; using heuristic")

    windows = await highlight.detect_highlights(
        source, clip_length_sec, max_clips=settings.max_clips
    )
    return windows, False


async def run_pipeline(job_id: str, source_url: str, clip_length_sec: float) -> None:
    settings = get_settings()
    job = await Job.get(job_id)
    if job is None:
        log.error("[pipeline] job %s disappeared before it started", job_id)
        return

    source: Path | None = None
    try:
        job.status = "processing"
        job.error = None
        await job.save()

        source = await ingest.download(source_url, job_id)

        windows, from_ai = await _select_windows(source, clip_length_sec)
        if windows:
            clips = await clipper.slice_windows(source, windows, job_id)
        else:
            clips = await clipper.slice_fixed(source, clip_length_sec, job_id)

        # The AI already wrote titles and descriptions per clip; only fill in
        # hashtags so we don't overwrite them with templated text.
        await metadata.populate(clips, keep_text=from_ai)

        if not clips:
            raise RuntimeError("Pipeline produced no clips")

        job.status = "done"
        await job.save()
        log.info("[pipeline] job %s done with %d clip(s)", job_id, len(clips))
    except Exception as exc:  # noqa: BLE001 - record the failure on the job
        log.exception("[pipeline] job %s failed", job_id)
        refreshed = await Job.get(job_id)
        if refreshed is not None:
            refreshed.status = "error"
            refreshed.error = str(exc)[:1000]
            await refreshed.save()
    finally:
        # Runs on failure too: a job that died during clipping still leaves a
        # multi-GB download behind, and a retry re-downloads anyway.
        _discard_source(source)


async def start_ingest(source_url: str, clip_length_sec: float) -> Job:
    """Create the Job and kick off processing, returning immediately."""
    from app import queue

    job = Job(
        sourceUrl=source_url, clipLengthSec=clip_length_sec, status="processing"
    )
    await job.insert()
    job_id = str(job.id)

    if await queue.enqueue_ingest(job_id, source_url, clip_length_sec):
        return job

    task = asyncio.create_task(run_pipeline(job_id, source_url, clip_length_sec))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return job
