"""FastAPI router for Sage Geopolitical Intelligence & Strategic Advisory Chatbot."""

from __future__ import annotations

import time
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.services.sage_service import (
    SUGGESTION_CATEGORIES,
    build_telemetry_snapshot,
    detect_entities,
    extract_followups,
    fetch_entity_context,
    generate_sage_reply,
)

router = APIRouter(prefix="/api/v1/sage", tags=["Sage AI"])


class SageChatMessage(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    role: str = Field(..., pattern="^(user|assistant|system)$", description="Role of the message sender")
    content: str = Field(..., description="Message text content")


class SageChatRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    message: str = Field(..., description="User question or prompt")
    history: list[SageChatMessage] = Field(default_factory=list, description="Prior conversation history")


class SageTelemetryHighlight(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    label: str = Field(..., description="Telemetry metric or indicator label")
    value: str = Field(..., description="Formatted indicator value")


class SageChatResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    reply: str = Field(..., description="Sage's markdown intelligence advice and analysis")
    telemetry_highlights: list[SageTelemetryHighlight] = Field(default_factory=list, description="Highlighted platform indicators")
    suggested_followups: list[str] = Field(default_factory=list, description="Contextual follow-up suggestions")
    model_used: str = Field(..., description="Model or engine that generated the response")
    latency_ms: int = Field(..., description="Processing latency in milliseconds")


@router.post("/chat", response_model=SageChatResponse)
async def sage_chat(payload: SageChatRequest) -> SageChatResponse:
    """Multi-turn conversational intelligence & strategic advisory endpoint."""
    user_msg = payload.message.strip()
    if not user_msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    start_time = time.monotonic()

    # 1. Build real-time platform telemetry snapshot
    telemetry = await build_telemetry_snapshot()

    # 2. Extract entities and fetch targeted context
    entities = detect_entities(user_msg)
    entity_context = await fetch_entity_context(entities)

    # 3. Format history
    history = [{"role": m.role, "content": m.content} for m in payload.history]

    # 4. Generate grounded reply
    reply, model_used = await generate_sage_reply(history, user_msg, telemetry, entity_context)
    followups = extract_followups(user_msg, reply, telemetry)

    latency_ms = int((time.monotonic() - start_time) * 1000)

    return SageChatResponse(
        reply=reply,
        telemetry_highlights=[SageTelemetryHighlight(**h) for h in telemetry.highlights()],
        suggested_followups=followups,
        model_used=model_used,
        latency_ms=latency_ms,
    )


@router.get("/context")
async def get_sage_context() -> dict[str, Any]:
    """Retrieve raw live platform telemetry snapshot used by Sage."""
    telemetry = await build_telemetry_snapshot()
    return {
        "defcon_level": telemetry.defcon_level,
        "global_avg_cii": telemetry.global_avg_cii,
        "top_volatile_countries": telemetry.top_volatile_countries,
        "chokepoints": telemetry.chokepoints,
        "top_aggression_pairs": telemetry.top_aggression_pairs,
        "high_risk_trade_routes": telemetry.high_risk_trade_routes,
        "active_naval_fleets": telemetry.active_naval_fleets,
        "recent_headlines": telemetry.recent_headlines,
        "recent_government_actions": telemetry.recent_government_actions,
        "recent_protests": telemetry.recent_protests,
        "prediction_markets": telemetry.prediction_markets,
        "data_gaps": telemetry.warnings,
    }


@router.get("/suggestions")
async def get_sage_suggestions() -> dict[str, Any]:
    """Retrieve curated starter questions across geopolitical & strategic advisory domains."""
    return {"categories": SUGGESTION_CATEGORIES}
