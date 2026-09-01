"""Download the source video.

Replaces the 281-line Node ingestService. yt-dlp is a Python package here, so
the binary bootstrapping, the stderr-regex progress watchdog and the output
path guessing all collapse into the library API.
"""

import asyncio
import contextlib
import logging
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yt_dlp

from app.config import get_settings
from app.services import media

log = logging.getLogger(__name__)

# Containers we accept straight from the downloader, in preference order.
_VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".mov", ".m4v")

# Extensions that mean "this URL is just a file", so we can skip yt-dlp.
_DIRECT_MEDIA_EXTS = _VIDEO_EXTS + (".ts", ".flv", ".avi")


class DownloadError(RuntimeError):
    pass


class _StallAbort(Exception):
    """Raised inside a yt-dlp progress hook to abort a stalled download."""


def _is_direct_media(url: str) -> bool:
    # .m3u8 deliberately excluded: yt-dlp handles HLS playlists properly.
    return urlparse(url).path.lower().endswith(_DIRECT_MEDIA_EXTS)


def _find_output(base: Path) -> Path | None:
    for ext in _VIDEO_EXTS:
        candidate = base.with_suffix(ext)
        if candidate.exists():
            return candidate
    matches = sorted(base.parent.glob(base.name + ".*"))
    return matches[0] if matches else None


def _cleanup(base: Path) -> None:
    for leftover in base.parent.glob(base.name + ".*"):
        with contextlib.suppress(OSError):
            leftover.unlink()


def _cleanup_fragments(base: Path) -> None:
    """Remove yt-dlp fragment files like <jobId>.f251.mp4 and .part files."""
    for pattern in (base.name + ".f*", base.name + "*.part"):
        for junk in base.parent.glob(pattern):
            with contextlib.suppress(OSError):
                junk.unlink()


def _resolve_downloaded_path(ydl, info: dict) -> Path | None:
    """Post-processing can change the extension, so trust requested_downloads."""
    for entry in info.get("requested_downloads") or []:
        filepath = entry.get("filepath") or entry.get("_filename")
        if filepath and Path(filepath).exists():
            return Path(filepath)
    with contextlib.suppress(Exception):
        guessed = Path(ydl.prepare_filename(info))
        if guessed.exists():
            return guessed
    return None


_BASE_YDL_OPTS: dict = {
    "noplaylist": True,
    "retries": 20,
    "fragment_retries": 20,
    "socket_timeout": 15,
    "concurrent_fragment_downloads": 5,
    "quiet": True,
    "no_warnings": True,
    "noprogress": True,
}


async def _ytdlp_download(url: str, base: Path) -> Path:
    settings = get_settings()
    state = {"last": time.monotonic(), "abort": False, "pct": ""}

    def hook(status: dict) -> None:
        state["last"] = time.monotonic()
        if state["abort"]:
            raise _StallAbort("download stalled")
        pct = (status.get("_percent_str") or "").strip()
        if pct and pct != state["pct"]:
            state["pct"] = pct
            log.debug("[ingest] %s %s", base.name, pct)

    def blocking(opts: dict) -> Path | None:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return _resolve_downloaded_path(ydl, info)

    async def watchdog() -> None:
        idle = settings.download_idle_timeout_sec
        while True:
            await asyncio.sleep(15)
            if time.monotonic() - state["last"] > idle:
                log.warning("[ingest] no progress for %ss, aborting", idle)
                state["abort"] = True
                return

    # Attempt 1: progressive/merged mp4. Attempt 2: anything, recoded to mp4.
    attempts = [
        {
            **_BASE_YDL_OPTS,
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "outtmpl": str(base) + ".%(ext)s",
            "progress_hooks": [hook],
        },
        {
            **_BASE_YDL_OPTS,
            "format": "best",
            "outtmpl": str(base) + ".%(ext)s",
            "progress_hooks": [hook],
            "postprocessors": [
                {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}
            ],
        },
    ]

    first_error: Exception | None = None
    for index, opts in enumerate(attempts, start=1):
        state["last"] = time.monotonic()
        state["abort"] = False
        watcher = asyncio.create_task(watchdog())
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(blocking, opts),
                timeout=settings.download_hard_timeout_sec,
            )
            if result is not None:
                return result
            found = _find_output(base)
            if found is not None:
                return found
            raise DownloadError("yt-dlp finished but produced no output file")
        except asyncio.TimeoutError:
            # The worker thread cannot be killed from here; the abort flag makes
            # it exit at its next progress callback.
            state["abort"] = True
            log.warning("[ingest] attempt %d hit the hard timeout", index)
            if first_error is None:
                first_error = DownloadError(
                    "Download exceeded "
                    + str(settings.download_hard_timeout_sec)
                    + "s"
                )
        except Exception as exc:  # noqa: BLE001 - fall through to next strategy
            log.warning("[ingest] attempt %d failed: %s", index, exc)
            if first_error is None:
                first_error = exc
        finally:
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher
            _cleanup_fragments(base)

    raise DownloadError(str(first_error) if first_error else "Download failed")


async def _http_download(url: str, base: Path) -> Path:
    settings = get_settings()
    target = base.with_suffix(".mp4")
    # The read timeout is the idle-stall guard: httpx raises if no bytes
    # arrive within the window, which is what the Node code hand-rolled.
    timeout = httpx.Timeout(
        connect=30.0,
        read=float(settings.download_idle_timeout_sec),
        write=30.0,
        pool=30.0,
    )
    log.info("[ingest] HTTP download %s", url)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with target.open("wb") as handle:
                async for chunk in response.aiter_bytes(1 << 20):
                    handle.write(chunk)
    return target


async def download(source_url: str, job_id: str) -> Path:
    """Fetch source_url into storage/downloads and return a usable mp4 path."""
    settings = get_settings()
    settings.downloads_dir.mkdir(parents=True, exist_ok=True)
    base = settings.downloads_dir / str(job_id)

    try:
        if _is_direct_media(source_url):
            output = await _http_download(source_url, base)
        else:
            log.info("[ingest] yt-dlp download %s", source_url)
            output = await _ytdlp_download(source_url, base)

        _cleanup_fragments(base)

        if not output.exists():
            resolved = _find_output(base)
            if resolved is None:
                raise DownloadError("Download finished but the output file is missing")
            output = resolved

        if output.stat().st_size < 1024:
            raise DownloadError("Downloaded file is too small to be a video")

        if output.suffix.lower() != ".mp4":
            log.info("[ingest] normalizing %s to mp4", output.suffix)
            normalized = base.with_suffix(".mp4")
            await media.transcode_to_mp4(output, normalized)
            with contextlib.suppress(OSError):
                output.unlink()
            output = normalized

        return output
    except Exception as exc:
        _cleanup(base)
        raise DownloadError(str(exc)) from exc
