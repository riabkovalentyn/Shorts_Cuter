"""Shared ffmpeg/ffprobe helpers.

The Node backend pulled binaries from @ffmpeg-installer. Here we resolve them
from the environment or PATH; the Docker image installs ffmpeg via apt, and the
README already tells local users to install it.
"""

import asyncio
import contextlib
import logging
import os
import shutil
from pathlib import Path

from app.config import get_settings

log = logging.getLogger(__name__)

_INSTALL_HINT = (
    "Install FFmpeg and make sure ffmpeg/ffprobe are on PATH. "
    "Windows: winget install Gyan.FFmpeg (or choco install ffmpeg). "
    "Debian/Ubuntu: apt-get install ffmpeg."
)


class FFmpegError(RuntimeError):
    pass


def _resolve(name: str, env_var: str) -> str:
    override = os.environ.get(env_var)
    if override:
        return override
    found = shutil.which(name)
    if not found:
        raise FFmpegError(f"{name} not found. {_INSTALL_HINT}")
    return found


def ffmpeg_path() -> str:
    return _resolve("ffmpeg", "FFMPEG_PATH")


def ffprobe_path() -> str:
    return _resolve("ffprobe", "FFPROBE_PATH")


def ensure_binaries() -> None:
    ffmpeg_path()
    ffprobe_path()


class FFmpegTimeout(FFmpegError):
    pass


async def _terminate(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError, OSError):
        proc.kill()
    with contextlib.suppress(Exception):
        await proc.wait()


async def run(
    cmd: str, args: list[str], timeout: float | None = None
) -> tuple[int, str]:
    """Run a binary, returning (exit_code, stderr). Never raises on non-zero.

    A `timeout` of None means wait forever; every caller should pass one, since
    a stalled ffmpeg would otherwise hang the job with nothing to kill it.
    """
    proc = await asyncio.create_subprocess_exec(
        cmd,
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        await _terminate(proc)
        raise FFmpegTimeout(
            f"{Path(cmd).name} timed out after {timeout}s and was killed"
        ) from None
    return proc.returncode or 0, stderr.decode("utf-8", errors="replace")


async def run_checked(
    cmd: str, args: list[str], timeout: float | None = None
) -> str:
    code, stderr = await run(cmd, args, timeout=timeout)
    if code != 0:
        tail = "\n".join(stderr.strip().splitlines()[-8:])
        raise FFmpegError(f"{Path(cmd).name} failed (exit {code}): {tail}")
    return stderr


async def probe_duration(path: Path) -> float:
    timeout = get_settings().probe_timeout_sec
    proc = await asyncio.create_subprocess_exec(
        ffprobe_path(),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        await _terminate(proc)
        raise FFmpegTimeout(f"ffprobe timed out after {timeout}s") from None
    if proc.returncode != 0:
        raise FFmpegError(f"ffprobe failed: {stderr.decode('utf-8', 'replace')[-400:]}")
    try:
        return float(stdout.decode().strip())
    except ValueError:
        return 0.0


async def transcode_to_mp4(src: Path, dst: Path) -> Path:
    """Normalize any container to a faststart mp4."""
    await run_checked(
        ffmpeg_path(),
        timeout=get_settings().analysis_timeout_sec,
        args=[
            "-y",
            "-i",
            str(src),
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
            str(dst),
        ],
    )
    return dst
