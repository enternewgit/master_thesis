from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

from ..music_ai.generator import generate_async

router = APIRouter()


MAX_DURATION_SECONDS = 120


class MusicGenerateBody(BaseModel):
    prompt: str
    provider: str = "mrt2"
    duration: int | None = None
    params: dict | None = None


@router.post("/generate")
async def generate_music(body: MusicGenerateBody):
    if body.duration is not None and (body.duration <= 0 or body.duration > MAX_DURATION_SECONDS):
        raise HTTPException(
            status_code=400,
            detail=f"'duration' must be in (0, {MAX_DURATION_SECONDS}] seconds",
        )
    try:
        res = await generate_async(body.prompt, provider=body.provider, duration=body.duration, params=body.params)
        iterable = res.get("iterable")
        content_type = res.get("content_type", "application/octet-stream")
        return StreamingResponse(iterable, media_type=content_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
