from fastapi import APIRouter, HTTPException, Query

from app.config import get_settings
from app.services import youtube

router = APIRouter()


@router.get("/url")
async def auth_url() -> dict:
    try:
        return {"url": await youtube.get_auth_url()}
    except youtube.YouTubeNotConfigured as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail="Failed to create auth URL: " + str(exc)
        ) from exc


@router.get("/callback")
async def auth_callback(code: str | None = Query(default=None)) -> dict:
    if not code:
        raise HTTPException(status_code=400, detail="code required")
    try:
        return await youtube.handle_oauth_callback(code)
    except youtube.YouTubeNotConfigured as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/status")
async def auth_status() -> dict:
    return {
        "configured": get_settings().youtube_configured,
        "connected": await youtube.is_connected(),
    }
