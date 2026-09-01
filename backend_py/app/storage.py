"""Mapping between absolute files on disk and their public /storage URLs."""

from pathlib import Path, PurePath

from app.config import get_settings


def to_public_url(file_path: str | Path | None) -> str | None:
    """Convert an absolute clip path into a browser-usable /storage/... URL.

    Handles rows written by the previous Node backend, which stored absolute
    Windows paths with backslashes.
    """
    if not file_path:
        return None

    raw = str(file_path)
    settings = get_settings()

    try:
        relative = Path(raw).resolve().relative_to(settings.storage_dir)
        return "/storage/" + relative.as_posix()
    except (ValueError, OSError):
        pass

    # Legacy fallback: slice at the last "storage" segment in the raw string.
    normalized = raw.replace("\\", "/")
    parts = PurePath(normalized).parts
    for index in range(len(parts) - 1, -1, -1):
        if parts[index].lower() == "storage":
            tail = "/".join(parts[index + 1 :])
            return "/storage/" + tail if tail else None
    return "/storage/" + normalized.lstrip("/")
