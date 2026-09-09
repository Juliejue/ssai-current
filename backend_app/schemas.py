from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RiskLevel(str, Enum):
    ordinary = "ordinary"
    elevated = "elevated"
    urgent = "urgent"


class NeedState(BaseModel):
    mood_id: str = "low"
    need_keys: list[str] = Field(default_factory=list, max_length=6)
    energy: int = Field(default=2, ge=0, le=4)
    social_mode: Literal["alone", "low_contact", "with_people", "either"] = "either"
    time_minutes: int | None = Field(default=None, ge=10, le=720)
    max_travel_minutes: int | None = Field(default=None, ge=5, le=180)
    budget_level: Literal["free", "low", "medium", "high", "unknown"] = "unknown"
    environment: Literal["indoor", "outdoor", "either"] = "either"
    avoid_tags: list[str] = Field(default_factory=list, max_length=8)
    confidence: float = Field(default=0.5, ge=0, le=1)
    needs_clarification: bool = False
    clarifying_question: str | None = Field(default=None, max_length=120)
    risk_level: RiskLevel = RiskLevel.ordinary
    risk_signals: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("mood_id")
    @classmethod
    def validate_mood(cls, value: str) -> str:
        allowed = {"low", "quiet", "noisy", "spark", "tired", "empty", "tight", "near", "fresh", "okay"}
        return value if value in allowed else "low"


class InterpretRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must not be blank")
        return value


class ClarifyOption(BaseModel):
    key: str = Field(max_length=40)
    label: str = Field(max_length=24)


class CorrectionOptions(BaseModel):
    """FR-03：能被一步纠正的四环。地点那一环不需要选项——换一批就是动作本身。"""

    state: list[ClarifyOption] = Field(default_factory=list, max_length=6)
    need: list[ClarifyOption] = Field(default_factory=list, max_length=6)
    constraint: list[ClarifyOption] = Field(default_factory=list, max_length=6)


class InterpretResponse(BaseModel):
    state: NeedState
    acknowledgement: str
    source: Literal["model", "rules"]
    # Everything below is rendered in the user's browser only. None of it is
    # persisted or logged: it quotes the user's own words back at them.
    state_label: str = ""
    evidence: list[str] = Field(default_factory=list, max_length=3)
    clarify_field: Literal["social_mode", "max_travel_minutes", "budget_level"] | None = None
    clarify_options: list[ClarifyOption] = Field(default_factory=list, max_length=3)
    corrections: CorrectionOptions = Field(default_factory=CorrectionOptions)


class Location(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class Geofence(BaseModel):
    """地点的坐标是公开信息，可以下发；用户的坐标不上传，围栏在浏览器里算。"""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_m: int = Field(ge=50, le=2000)


class RecommendRequest(BaseModel):
    state: NeedState
    location: Location | None = None
    rejected_place_ids: list[str] = Field(default_factory=list, max_length=20)
    limit: int = Field(default=3, ge=1, le=10)


class Recommendation(BaseModel):
    recommendation_id: str
    place_id: str
    place_name: str
    action: str
    reason: str
    score: float = Field(ge=0, le=1)
    distance_km: float | None = None
    walking_minutes: int | None = None
    distance_source: Literal["amap", "prototype_estimate"] = "prototype_estimate"
    map_verified: bool = False
    navigation_url: str | None = None
    transport: str | None = None
    suggested_duration: str | None = None
    cost: str | None = None
    see: str | None = None
    tradeoffs: list[str] = Field(default_factory=list)
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    role: Literal["primary", "alternate"] = "alternate"
    reach_minutes: int | None = None
    time_to_relief: Literal["now", "near", "later"] = "near"
    relief_label: str = ""
    # 状态 → 需求 → 命中属性. Every entry is traceable to the stored NeedState
    # and to a field on the reviewed place record (FR-20).
    reason_chain: list[str] = Field(default_factory=list, max_length=3)
    # Honest sampling (FR-10b / FR-19b): Current has no verified visit feedback
    # yet, so no place is allowed to present an average as if it were a fact.
    sample_size: int = 0
    low_support: bool = True
    # 营业状态（FR-07）。estimate 只降权并明说是估算；verified 才是硬约束。
    open_state: Literal["always_open", "open", "likely_closed", "closed", "unknown"] = "unknown"
    open_label: str = ""
    hours_source: Literal["verified", "category_estimate", "always_open", "unknown"] = "unknown"
    # 只有人工核对过坐标的地点才有围栏（FR-08 L1）。为 None 时前端退回手动确认。
    geofence: Geofence | None = None
    # US-06：让用户选地图。GCJ-02 与 WGS-84 已按各家坐标系分别转换好。
    map_links: dict[str, str] = Field(default_factory=dict)


class RecommendResponse(BaseModel):
    recommendations: list[Recommendation]
    blocked_by_safety: bool = False
    safety_message: str | None = None
    no_good_match: bool = False
    fallback_note: str | None = None


ProductEventName = Literal[
    "natural_language_started",
    "natural_language_interpreted",
    "recommendation_shown",
    "recommendation_accepted",
    "recommendation_rejected",
    "navigation_opened",
    "arrival_confirmed",
    "outcome_saved",
]


class ProductEvent(BaseModel):
    name: ProductEventName
    session_id: str = Field(min_length=8, max_length=80)
    recommendation_id: str | None = Field(default=None, max_length=80)
    place_id: str | None = Field(default=None, max_length=80)
    properties: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class OutcomeDeleteRequest(BaseModel):
    """FR-12 / §M6：记忆可删除。承诺过就要给得出出口。"""

    session_id: str = Field(min_length=8, max_length=80)
    recommendation_id: str = Field(min_length=8, max_length=80)


class OutcomeRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=80)
    recommendation_id: str = Field(min_length=8, max_length=80)
    place_id: str = Field(min_length=1, max_length=80)
    change_score: int = Field(ge=-3, le=3)
    factor_keys: list[str] = Field(default_factory=list, max_length=12)
    visibility: Literal["private", "anonymous"] = "private"
    note: str | None = Field(default=None, max_length=80)
    # 哪一环对/错（FR-09 / SP-4）。冷启动阶段最有价值的一列。
    mismatch_stage: Literal["none", "state", "need", "constraint", "place"] = "none"
    # 在场证明（FR-08）。浏览器只报结论，服务端会往下降级，绝不采信更高的声明。
    presence_level: Literal["geofence_dwell", "dwell_only", "self_reported"] = "self_reported"
    dwell_minutes: int = Field(default=0, ge=0, le=1440)
