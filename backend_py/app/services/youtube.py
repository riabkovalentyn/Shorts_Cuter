"""YouTube OAuth + upload.

Uses google-auth-oauthlib for the consent flow and google-api-python-client for
a resumable upload. Both libraries are blocking, so calls are pushed onto a
worker thread.
"""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from app.config import get_settings
from app.models import Clip, Token, YouTubeRef

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_URI = "https://oauth2.googleapis.com/token"
AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
PROVIDER = "youtube"


class YouTubeNotConfigured(RuntimeError):
    pass


class YouTubeNotConnected(RuntimeError):
    pass


def _client_config() -> dict:
    settings = get_settings()
    if not settings.youtube_configured:
        raise YouTubeNotConfigured(
            "Missing GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET env vars"
        )
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": AUTH_URI,
            "token_uri": TOKEN_URI,
            "redirect_uris": [settings.yt_redirect_uri],
        }
    }


def _flow() -> Flow:
    settings = get_settings()
    return Flow.from_client_config(
        _client_config(), scopes=SCOPES, redirect_uri=settings.yt_redirect_uri
    )


async def get_auth_url() -> str:
    flow = _flow()
    url, _state = flow.authorization_url(
        access_type="offline", prompt="consent", include_granted_scopes="true"
    )
    return url


async def handle_oauth_callback(code: str) -> dict:
    flow = _flow()
    await asyncio.to_thread(flow.fetch_token, code=code)
    creds = flow.credentials

    if not creds.refresh_token:
        raise RuntimeError(
            "No refresh_token received. Ensure access_type=offline and "
            "prompt=consent were used."
        )

    now = datetime.now(timezone.utc)
    expiry = int(creds.expiry.timestamp() * 1000) if creds.expiry else None

    token = await Token.find_one(Token.provider == PROVIDER)
    if token is None:
        token = Token(provider=PROVIDER, refreshToken=creds.refresh_token)

    token.refreshToken = creds.refresh_token
    token.accessToken = creds.token
    token.scope = " ".join(creds.scopes or SCOPES)
    token.tokenType = "Bearer"
    token.expiryDate = expiry
    token.updatedAt = now
    await token.save()

    return {"ok": True, "tokenId": str(token.id)}


async def is_connected() -> bool:
    token = await Token.find_one(Token.provider == PROVIDER)
    return bool(token and token.refreshToken)


async def _credentials() -> Credentials:
    settings = get_settings()
    token = await Token.find_one(Token.provider == PROVIDER)
    if not token or not token.refreshToken:
        raise YouTubeNotConnected("YouTube not connected: no refresh token stored")
    return Credentials(
        token=None,
        refresh_token=token.refreshToken,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        token_uri=TOKEN_URI,
        scopes=SCOPES,
    )


def _upload_blocking(creds: Credentials, path: Path, body: dict) -> str:
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    media_body = MediaFileUpload(
        str(path), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True
    )
    request = youtube.videos().insert(
        part="snippet,status", body=body, media_body=media_body
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log.info("[youtube] upload %d%%", int(status.progress() * 100))
    return response.get("id", "unknown")


async def upload_clip(clip: Clip) -> Clip:
    path = Path(clip.filePath) if clip.filePath else None
    if path is None or not path.exists():
        raise FileNotFoundError("Clip file not found: " + str(clip.filePath))

    creds = await _credentials()
    body = {
        "snippet": {
            "title": (clip.title or "Shorts Clip")[:100],
            "description": clip.description or "",
            "tags": [tag.lstrip("#") for tag in (clip.hashtags or [])],
            "categoryId": "22",
        },
        # Deliberately private: the user reviews before publishing.
        "status": {"privacyStatus": "private"},
    }

    video_id = await asyncio.to_thread(_upload_blocking, creds, path, body)

    clip.status = "uploaded"
    clip.youtube = YouTubeRef(
        id=video_id, publishedAt=datetime.now(timezone.utc).isoformat()
    )
    await clip.save()
    log.info("[youtube] uploaded clip %s as %s", clip.id, video_id)
    return clip
