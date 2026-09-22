from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .community import delete_contribution, list_approved_contributions, submit_contribution
from .interpretation import interpret
from .i18n import ui
from .map_provider import AmapClient, MapProviderError, static_map_png
from .realtime_asr import build_asr_connect_url, is_configured as realtime_asr_is_configured
from .presence import verify as verify_presence
from .relay import append_event, create_session, normalize_code, read_events, safe_payload, valid_code
from .reflect import reflect_quietly
from .recommender import load_catalog, recommend_with_live_context, warm_discovery
from .schemas import (
    CommunityContributionDelete,
    CommunityContributionList,
    CommunityContributionRequest,
    CommunityContributionResponse,
    InterpretRequest,
    InterpretResponse,
    Location,
    OutcomeDeleteRequest,
    OutcomeRequest,
    ProductEvent,
    RelayEventRequest,
    RelayReadResponse,
    RelaySessionResponse,
    ReverseLocationResponse,
    RecommendRequest,
    ReflectRequest,
    ReflectResponse,
    RecommendResponse,
    RiskLevel,
)
from .space_profiles import refresh_space_profile
from .storage import delete_outcome, safe_event_properties, store_outcome, store_product_event, store_recommendations


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


@app.post("/api/v1/location/reverse", response_model=ReverseLocationResponse)
async def reverse_location(payload: Location) -> ReverseLocationResponse:
    """Resolve city without putting a user's coordinates in our logs or database."""
    try:
        result = await AmapClient().reverse_geocode(
            longitude=payload.longitude,
            latitude=payload.latitude,
        )
    except MapProviderError as error:
        raise HTTPException(status_code=503, detail="城市暂时识别不了") from error
    return ReverseLocationResponse(**result.__dict__)


@app.post(
    "/api/v1/community/contributions",
    response_model=CommunityContributionResponse,
    status_code=202,
)
async def community_submit(payload: CommunityContributionRequest) -> CommunityContributionResponse:
    contribution_id, receipt_token, persisted = await submit_contribution(payload)
    return CommunityContributionResponse(
        persisted=persisted,
        contribution_id=contribution_id,
        receipt_token=receipt_token,
    )


@app.get("/api/v1/community/contributions", response_model=CommunityContributionList)
async def community_list(city: str | None = None) -> CommunityContributionList:
    clean_city = city.strip()[:40] if city else None
    contributions = await list_approved_contributions(clean_city or None)
    return CommunityContributionList(contributions=contributions)


@app.post("/api/v1/community/contributions/delete", status_code=202)
async def community_delete(payload: CommunityContributionDelete) -> dict[str, bool]:
    deleted = await delete_contribution(payload.contribution_id, payload.receipt_token)
    return {"accepted": True, "deleted": deleted}


@app.post("/api/v1/relay/sessions", response_model=RelaySessionResponse)
async def relay_session_create() -> RelaySessionResponse:
    code, expires_at, durable = await create_session()
    return RelaySessionResponse(code=code, expires_at=expires_at.isoformat(), durable=durable)


@app.get("/api/v1/relay/{code}", response_model=RelayReadResponse)
async def relay_events(code: str, after: int = 0) -> RelayReadResponse:
    clean_code = normalize_code(code)
    if not valid_code(clean_code):
        raise HTTPException(status_code=404, detail="会话不存在或已经结束")
    events, expires_at, durable = await read_events(clean_code, max(0, after))
    if events is None or expires_at is None:
        raise HTTPException(status_code=404, detail="会话不存在或已经结束")
    return RelayReadResponse(
        code=clean_code,
        expires_at=expires_at.isoformat(),
        durable=durable,
        events=events,
    )


@app.post("/api/v1/relay/{code}/events", status_code=202)
async def relay_event(code: str, payload: RelayEventRequest) -> dict[str, bool | int]:
    try:
        safe_payload(payload.event_type, payload.payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    sequence, durable = await append_event(code, payload.event_type, payload.payload)
    if sequence is None:
        raise HTTPException(status_code=404, detail="会话不存在或已经结束")
    return {"accepted": True, "sequence": sequence, "durable": durable}


@app.get("/api/v1/asr/signature")
async def asr_signature() -> dict[str, str | int]:
    try:
        return build_asr_connect_url()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _preferred_asr_provider(request: Request, tencent_configured: bool) -> str:
    """Choose a voice path without asking the user about network geography.

    Tencent classifies Hong Kong, Macao, Taiwan and other non-mainland traffic
    as cross-border realtime ASR. Until that entitlement is enabled, browsers
    outside mainland China should start their own dictation path first. We only
    use Vercel's country header for this routing decision and never return or
    store the region itself.
    """
    if not tencent_configured:
        return "browser"
    country = request.headers.get("x-vercel-ip-country", "").strip().upper()
    if country and country != "CN" and not _env_flag("ASR_CROSS_BORDER_ENABLED"):
        return "browser"
    return "tencent"


@app.get("/api/v1/asr/capabilities")
async def asr_capabilities(request: Request, response: Response) -> dict[str, bool | str]:
    """Tell the client which voice path to start; never expose credentials."""
    response.headers["Cache-Control"] = "no-store"
    configured = realtime_asr_is_configured()
    return {
        "tencent_realtime": configured,
        "preferred_provider": _preferred_asr_provider(request, configured),
    }


@app.get("/api/v1/map/static")
async def static_map_route(lat: float, lng: float, w: int = 640, h: int = 260) -> Response:
    """地图图片代理。key 留在服务端，浏览器只看得见我们的域名。

    只接受地点坐标（公开信息）。用户自己的位置不经过这里，也不该经过。
    """
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise HTTPException(status_code=400, detail="坐标超出范围")
    # 限死尺寸：这是给我们自己的卡片用的，不是一个通用图片代理。
    width, height = max(120, min(w, 1024)), max(80, min(h, 512))
    try:
        png = await static_map_png(lng, lat, width, height)
    except MapProviderError:
        # 地图挂了不该让整张卡片出错，前端会把这块藏掉。
        raise HTTPException(status_code=503, detail="地图暂时取不到")
    return Response(
        content=png,
        media_type="image/png",
        # 地点不会动，缓存一天，省配额也省等待。
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.post("/api/v1/interpret", response_model=InterpretResponse)
async def interpret_route(payload: InterpretRequest) -> InterpretResponse:
    # 模型读这句话要 4–6 秒，周边搜索要 2–4 秒，两件事互不依赖。
    # 用户还在看「我听到的」那一屏时，地图结果就已经备好了——
    # 等他点到推荐，那一步几乎不用等。
    warm = asyncio.create_task(warm_discovery(payload.location)) if payload.location else None
    try:
        return await interpret(payload.text, payload.lang)
    finally:
        if warm and not warm.done():
            # 预热失败不影响任何事，但也不能留一个没人管的任务。
            warm.add_done_callback(lambda task: task.exception())


@app.post("/api/v1/reflect", response_model=ReflectResponse)
async def reflect_route(payload: ReflectRequest) -> ReflectResponse:
    """把离开之后的一句话变成这次到访的反馈。

    模型没接住就返回空分数，前端退回自己选——绝不替用户猜一个分数塞进他的记录。
    """
    result = await reflect_quietly(
        payload.text,
        place_name=payload.place_name,
        pre_mood=payload.pre_mood,
        options=payload.options,
        lang=payload.lang,
    )
    return ReflectResponse(**result)


@app.post("/api/v1/recommendations", response_model=RecommendResponse)
async def recommendations_route(
    payload: RecommendRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> RecommendResponse:
    if payload.state.risk_level == RiskLevel.urgent:
        return RecommendResponse(
            recommendations=[],
            blocked_by_safety=True,
            safety_message=ui("safety", payload.lang) or "我现在更在意你和身边的人是否安全。请先联系身边可信任的人；如果你可能马上伤害自己或他人，请立即联系当地急救或报警服务。",
        )
    recommendations = await recommend_with_live_context(payload)

    # 用户刚说完「太远了」，结果一个都没有——这是纠错之后最糟的结局。
    # US-03「近处先接住」：放开上限重来一次，给最近的几个，并且说清楚它们超了。
    relaxed_note = None
    if not recommendations and payload.state.max_travel_minutes is not None:
        relaxed = payload.model_copy(update={"state": payload.state.model_copy(update={"max_travel_minutes": None})})
        recommendations = await recommend_with_live_context(relaxed)
        if recommendations:
            relaxed_note = (ui("relaxed_note", payload.lang, minutes=payload.state.max_travel_minutes)
                            or f"{payload.state.max_travel_minutes} 分钟内我没找到合适的。下面是最近的几个，都超了——你看要不要将就一下。")

    session_id = request.headers.get("x-session-id", "")
    if 8 <= len(session_id) <= 80:
        # Neon may need several seconds to wake or establish a cross-border TLS
        # connection. The decision log matters, but the user must not wait for it
        # before seeing the recommendation. Starlette runs this after sending the
        # response body while still completing it within the request lifecycle.
        background_tasks.add_task(store_recommendations, session_id, payload.state, recommendations)
    # Never pretend a weak shortlist is a good one (SP-3 / 守则 6).
    no_good_match = not recommendations or recommendations[0].score < 0.35
    all_shut = bool(recommendations) and all(
        item.open_state in {"likely_closed", "closed"} for item in recommendations
    )
    if relaxed_note:
        note = relaxed_note
    elif all_shut:
        note = ui("all_shut", payload.lang) or "这个点开着门的地方不多，下面这几个多半已经打烊了。要不先去没有门的地方走走？"
    elif not recommendations and payload.state.place_types and payload.location is None:
        note = ("Turn on location and I’ll look for a real nearby match."
                if payload.lang == "en" else
                "开启定位，我来找附近真正匹配的地方。")
    elif not recommendations and payload.state.place_types:
        note = ("I couldn’t find a close match nearby yet. Try another activity or a wider area."
                if payload.lang == "en" else
                "附近暂时没找到真正匹配的场地。可以换个项目，或者扩大范围。")
    elif no_good_match:
        note = ui("no_good_match", payload.lang) or "这几个我不太有把握，先给你最近的一个；不合适就说一声。"
    else:
        note = None
    return RecommendResponse(
        recommendations=recommendations,
        no_good_match=no_good_match or all_shut or bool(relaxed_note),
        fallback_note=note,
    )


@app.post("/api/v1/events", status_code=202)
async def product_event(payload: ProductEvent) -> dict[str, bool]:
    # Deliberately never log free text, coordinates, or user identifiers.
    logger.info(json.dumps({"event": "product_event", "name": payload.name, "session_id": payload.session_id, "recommendation_id": payload.recommendation_id, "place_id": payload.place_id, "properties": safe_event_properties(payload)}, ensure_ascii=False))
    persisted = await store_product_event(payload)
    return {"accepted": True, "persisted": persisted}


def _place_by_id(place_id: str) -> dict | None:
    return next((p for p in load_catalog()["PLACES"] if p["placeId"] == place_id), None)


@app.post("/api/v1/outcomes", status_code=202)
async def outcome(payload: OutcomeRequest, background_tasks: BackgroundTasks) -> dict[str, bool | str]:
    # 浏览器的在场声明只会被往下降，永远不会被采信为更高等级（FR-08 L3）。
    level, presence_reason = verify_presence(payload.presence_level, payload.dwell_minutes, _place_by_id(payload.place_id))
    payload = payload.model_copy(update={"presence_level": level})
    # Never log the optional note, even when the user explicitly shares it anonymously.
    logger.info(json.dumps({"event": "outcome_saved", "session_id": payload.session_id, "recommendation_id": payload.recommendation_id, "place_id": payload.place_id, "change_score": payload.change_score, "factor_count": len(payload.factor_keys), "visibility": payload.visibility, "mismatch_stage": payload.mismatch_stage, "presence_level": level, "dwell_minutes": payload.dwell_minutes}, ensure_ascii=False))
    persisted = await store_outcome(payload)
    if persisted and level == "geofence_dwell":
        background_tasks.add_task(refresh_space_profile, payload.place_id)
    return {"accepted": True, "persisted": persisted, "presence_level": level, "presence_reason": presence_reason}


@app.post("/api/v1/outcomes/delete", status_code=202)
async def outcome_delete(payload: OutcomeDeleteRequest) -> dict[str, bool]:
    """记忆可删除（FR-12 / §M6）。删除本身不留正文，只记一次「发生过删除」。"""
    logger.info(json.dumps({"event": "outcome_deleted", "session_id": payload.session_id, "recommendation_id": payload.recommendation_id}, ensure_ascii=False))
    deleted = await delete_outcome(payload)
    return {"accepted": True, "deleted": deleted}
