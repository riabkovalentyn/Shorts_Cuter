"""HTTP-level tests that need no MongoDB.

These exercise the paths that short-circuit before any DB access: health,
request validation, invalid ObjectIds and the /storage guard. They pin the
error envelope shape, which the frontend depends on (it reads `error`, not
FastAPI's default `detail`).
"""

import asyncio
import os
import tempfile
from pathlib import Path

import httpx
import pytest

# StaticFiles is mounted at import time, so the storage dir must exist first.
_STORAGE = Path(tempfile.mkdtemp(prefix="shorts-test-storage-"))
os.environ["STORAGE_DIR"] = str(_STORAGE)
os.environ["MONGO_URI"] = "mongodb://localhost:27017/test_db"
os.environ.pop("REDIS_URL", None)

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _pinned_storage(monkeypatch):
    """Keep settings pointed at the mounted dir regardless of test order."""
    monkeypatch.setenv("STORAGE_DIR", str(_STORAGE))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def call(method: str, path: str, **kwargs) -> httpx.Response:
    async def _run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(_run())


# --------------------------------------------------------------------------
# basics
# --------------------------------------------------------------------------


def test_health():
    response = call("GET", "/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_root_reports_api_info():
    response = call("GET", "/")
    assert response.status_code == 200
    assert response.json()["name"] == "Shorts Cuter API"


# --------------------------------------------------------------------------
# error envelope - the frontend reads `error`, not `detail`
# --------------------------------------------------------------------------


def test_missing_source_url_returns_error_key():
    response = call("POST", "/api/projects", json={})
    assert response.status_code == 400
    body = response.json()
    assert "error" in body and "detail" not in body


def test_non_http_source_url_rejected():
    response = call("POST", "/api/projects", json={"sourceUrl": "ftp://x/y.mp4"})
    assert response.status_code == 400
    assert "http" in response.json()["error"].lower()


def test_invalid_job_id_is_404_not_500():
    response = call("GET", "/api/jobs/not-an-object-id")
    assert response.status_code == 404
    assert response.json() == {"error": "Not found"}


def test_invalid_clip_id_is_404_not_500():
    response = call("POST", "/api/clips/not-an-object-id/upload")
    assert response.status_code == 404
    assert response.json() == {"error": "Not found"}


# --------------------------------------------------------------------------
# /storage guard
# --------------------------------------------------------------------------


def test_zero_byte_file_returns_404():
    """Empty files otherwise make the browser raise RangeNotSatisfiable."""
    empty = _STORAGE / "clips"
    empty.mkdir(parents=True, exist_ok=True)
    (empty / "empty.mp4").write_bytes(b"")

    response = call("GET", "/storage/clips/empty.mp4")
    assert response.status_code == 404
    assert response.json() == {"error": "File is empty"}


def test_real_file_is_served():
    clips = _STORAGE / "clips"
    clips.mkdir(parents=True, exist_ok=True)
    (clips / "ok.txt").write_bytes(b"hello")

    response = call("GET", "/storage/clips/ok.txt")
    assert response.status_code == 200
    assert response.content == b"hello"


def test_encoded_path_traversal_is_rejected():
    secret = _STORAGE.parent / "outside-secret.txt"
    secret.write_text("nope")
    response = call("GET", "/storage/%2e%2e/outside-secret.txt")
    assert response.status_code == 400


def test_missing_storage_file_is_404():
    response = call("GET", "/storage/clips/does-not-exist.mp4")
    assert response.status_code == 404
