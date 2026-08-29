"""FastAPI route for S.A.G.E Kokoro TTS audio synthesis."""

from __future__ import annotations

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from api.services.kokoro_tts_service import synthesize_speech

logger = logging.getLogger("sage_tts")

router = APIRouter(prefix="/api/v1/sage", tags=["Sage TTS"])


class SageTTSRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    text: str = Field(..., description="Text to synthesize into speech")
    voice: Optional[str] = Field(None, description="Optional Kokoro voice ID override")
    speed: Optional[float] = Field(None, ge=0.5, le=2.0, description="Optional speed multiplier (0.5 - 2.0)")


@router.post("/tts")
async def sage_tts(payload: SageTTSRequest) -> Response:
    """Synthesize text into natural WAV audio stream via local Kokoro TTS model."""
    raw_text = payload.text.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="Text field cannot be empty")

    try:
        wav_bytes = await synthesize_speech(raw_text, voice=payload.voice, speed=payload.speed)
        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={
                "Content-Type": "audio/wav",
                "Content-Length": str(len(wav_bytes)),
                "Cache-Control": "public, max-age=3600",
                "Content-Disposition": "inline; filename=sage_speech.wav",
            },
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        logger.error("Kokoro TTS synthesis failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"TTS synthesis failed: {exc}")
