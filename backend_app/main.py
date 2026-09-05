from __future__ import annotations

import json
import logging
import os
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .interpretation import interpret
from .realtime_asr import build_asr_connect_url
from .recommender import recommend_with_live_context
from .schemas import (
    InterpretRequest,
    InterpretResponse,
    OutcomeRequest,
    ProductEvent,
    RecommendRequest,
    RecommendResponse,
    RiskLevel,
)
from .storage import safe_event_properties, store_outcome, store_product_event, store_recommendations


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("current")

app = FastAPI(title="Current API", version="0.1.0")
origins = [item.strip() for item in os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",") if item.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Session-Id"],
)


@app.middleware("http")
async def structured_logging(request: Request, call_next):
    started = time.monotonic()
    request_id = request.headers.get("x-vercel-id") or uuid.uuid4().hex
    try:
        response = await call_next(request)
        logger.info(json.dumps({"event": "request_done", "route": request.url.path, "status": response.status_code, "duration_ms": round((time.monotonic() - started) * 1000), "request_id": request_id}))
        return response
    except Exception:
        logger.exception(json.dumps({"event": "request_failed", "route": request.url.path, "duration_ms": round((time.monotonic() - started) * 1000), "request_id": request_id}))
        raise


@app.get("/api/v1/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/asr/signature")
async def asr_signature() -> dict[str, str | int]:
    try:
        return build_asr_connect_url()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/api/v1/interpret", response_model=InterpretResponse)
async def interpret_route(payload: InterpretRequest) -> InterpretResponse:
    return await interpret(payload.text)


@app.post("/api/v1/recommendations", response_model=RecommendResponse)
async def recommendations_route(payload: RecommendRequest, request: Request) -> RecommendResponse:
    if payload.state.risk_level == RiskLevel.urgent:
        return RecommendResponse(
            recommendations=[],
            blocked_by_safety=True,
            safety_message="我现在更在意你是否安全。请先联系身边可信任的人；如果你可能马上伤害自己，请立即联系当地急救或报警服务。",
        )
    recommendations = await recommend_with_live_context(payload)
    session_id = request.headers.get("x-session-id", "")
    if 8 <= len(session_id) <= 80:
        await store_recommendations(session_id, payload.state, recommendations)
    return RecommendResponse(recommendations=recommendations)


@app.post("/api/v1/events", status_code=202)
async def product_event(payload: ProductEvent) -> dict[str, bool]:
    # Deliberately never log free text, coordinates, or user identifiers.
    logger.info(json.dumps({"event": "product_event", "name": payload.name, "session_id": payload.session_id, "recommendation_id": payload.recommendation_id, "place_id": payload.place_id, "properties": safe_event_properties(payload)}, ensure_ascii=False))
    persisted = await store_product_event(payload)
    return {"accepted": True, "persisted": persisted}


@app.post("/api/v1/outcomes", status_code=202)
async def outcome(payload: OutcomeRequest) -> dict[str, bool]:
    # Never log the optional note, even when the user explicitly shares it anonymously.
    logger.info(json.dumps({"event": "outcome_saved", "session_id": payload.session_id, "recommendation_id": payload.recommendation_id, "place_id": payload.place_id, "change_score": payload.change_score, "factor_count": len(payload.factor_keys), "visibility": payload.visibility}, ensure_ascii=False))
    persisted = await store_outcome(payload)
    return {"accepted": True, "persisted": persisted}
