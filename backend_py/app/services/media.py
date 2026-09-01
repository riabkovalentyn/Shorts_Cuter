"""Shared ffmpeg/ffprobe helpers.

The Node backend pulled binaries from @ffmpeg-installer. Here we resolve them
from the environment or PATH; the Docker image installs ffmpeg via apt, and the
README already tells local users to install it.
"""

import asyncio
import logging
import os
import shutil
from pathlib import Path

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


async def run(cmd: str, args: list[str]) -> tuple[int, str]:
    """Run a binary, returning (exit_code, stderr). Never raises on non-zero."""
    proc = await asyncio.create_subprocess_exec(
        cmd,
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    return proc.returncode or 0, stderr.decode("utf-8", errors="replace")


async def run_checked(cmd: str, args: list[str]) -> str:
    code, stderr = await run(cmd, args)
    if code != 0:
        tail = "\n".join(stderr.strip().splitlines()[-8:])
        raise FFmpegError(f"{Path(cmd).name} failed (exit {code}): {tail}")
    return stderr


async def probe_duration(path: Path) -> float:
    proc = await asyncio.create_subprocess_exec(
        ffprobe_path(),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
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
        [
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
