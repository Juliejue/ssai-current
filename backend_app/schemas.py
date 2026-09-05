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


class InterpretResponse(BaseModel):
    state: NeedState
    acknowledgement: str
    source: Literal["model", "rules"]


class Location(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


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


class RecommendResponse(BaseModel):
    recommendations: list[Recommendation]
    blocked_by_safety: bool = False
    safety_message: str | None = None


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


class OutcomeRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=80)
    recommendation_id: str = Field(min_length=8, max_length=80)
    place_id: str = Field(min_length=1, max_length=80)
    change_score: int = Field(ge=-3, le=3)
    factor_keys: list[str] = Field(default_factory=list, max_length=12)
    visibility: Literal["private", "anonymous"] = "private"
    note: str | None = Field(default=None, max_length=80)
