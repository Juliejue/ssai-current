from __future__ import annotations

import json
import os
import re

import httpx
from pydantic import ValidationError

from .schemas import InterpretResponse, NeedState, RiskLevel


MOOD_RULES: dict[str, tuple[str, ...]] = {
    "quiet": ("安静", "太吵", "不想听", "别说话"),
    "noisy": ("脑子停不下来", "想太多", "一直想", "坐不住", "很乱"),
    "spark": ("灵感", "没方向", "想创作", "想看看"),
    "tired": ("很累", "没睡", "困", "疲惫", "躺不住"),
    "empty": ("空落落", "没着落", "空空", "没意思"),
    "tight": ("发紧", "绷着", "喘不过", "心慌"),
    "near": ("想有人", "陪我", "一个人难受", "有人在"),
    "fresh": ("换个地方", "待腻", "没见过", "出去看看"),
    "okay": ("还行", "挺好", "没事", "随便走走"),
    "low": ("低落", "难受", "委屈", "没力气", "不开心", "糟糕"),
}

NEED_RULES: dict[str, tuple[str, ...]] = {
    "hide": ("不想见人", "不被看见", "躲", "一个人"),
    "sit": ("坐一会", "坐很久", "不想动"),
    "walk": ("走走", "散步", "一直走", "走一会"),
    "free": ("不花钱", "不想花钱", "没钱", "便宜", "预算低"),
    "green": ("树", "绿色", "公园", "自然"),
    "new": ("没见过", "新鲜", "换个地方"),
    "sound": ("听音乐", "听点声音", "唱片"),
    "people": ("有人在", "有人就行", "生活气"),
    "loud": ("吵一点", "热闹", "蹦迪"),
    "slow": ("慢下来", "安静", "缓一缓"),
    "hands": ("手上有事", "做点什么", "翻书"),
    "breathe": ("喘口气", "透气", "发紧"),
    "nothing": ("不想决定", "你替我选", "随便", "都可以"),
}

URGENT_PATTERNS = ("不想活", "想死", "结束生命", "自杀", "伤害自己")
ELEVATED_PATTERNS = ("撑不住", "失控", "崩溃", "活不下去")


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(item in text for item in patterns)


def interpret_with_rules(text: str) -> InterpretResponse:
    mood_scores = {mood: sum(text.count(token) for token in tokens) for mood, tokens in MOOD_RULES.items()}
    mood_id = max(mood_scores, key=mood_scores.get)
    if mood_scores[mood_id] == 0:
        mood_id = "low"

    needs = [key for key, tokens in NEED_RULES.items() if _contains_any(text, tokens)]
    urgent = _contains_any(text, URGENT_PATTERNS)
    elevated = not urgent and _contains_any(text, ELEVATED_PATTERNS)
    risk_level = RiskLevel.urgent if urgent else RiskLevel.elevated if elevated else RiskLevel.ordinary

    energy = 2
    if _contains_any(text, ("没力气", "很累", "动不了", "不想动")):
        energy = 1
    elif _contains_any(text, ("有力气", "想运动", "想跳", "想跑")):
        energy = 4

    budget = "free" if _contains_any(text, ("不花钱", "不想花钱", "没钱", "免费")) else "low" if "便宜" in text else "unknown"
    social = "alone" if _contains_any(text, ("不想见人", "一个人", "别跟人说话")) else "with_people" if _contains_any(text, ("想有人", "热闹", "陪我")) else "either"

    state = NeedState(
        mood_id=mood_id,
        need_keys=needs[:6],
        energy=energy,
        social_mode=social,
        budget_level=budget,
        confidence=0.58 if mood_scores[mood_id] else 0.35,
        risk_level=risk_level,
        risk_signals=["explicit_self_harm_language"] if urgent else ["severe_distress_language"] if elevated else [],
    )
    return InterpretResponse(
        state=state,
        acknowledgement="我听见了。先不逼你解释清楚，我按你刚刚说的替你缩小范围。",
        source="rules",
    )


SYSTEM_PROMPT = """你是 Current 的需求解释器。把用户的中文自然表达转换为 JSON，不能诊断、不能给人格贴标签。
只输出 JSON，字段必须符合：
{
  "mood_id": "low|quiet|noisy|spark|tired|empty|tight|near|fresh|okay",
  "need_keys": ["hide|sit|walk|free|green|new|sound|people|loud|slow|hands|breathe|nothing"],
  "energy": 0-4,
  "social_mode": "alone|low_contact|with_people|either",
  "time_minutes": 10-720 或 null,
  "max_travel_minutes": 5-180 或 null,
  "budget_level": "free|low|medium|high|unknown",
  "environment": "indoor|outdoor|either",
  "avoid_tags": [],
  "confidence": 0-1,
  "needs_clarification": boolean,
  "clarifying_question": string 或 null,
  "risk_level": "ordinary|elevated|urgent",
  "risk_signals": []
}
只有缺失会改变推荐的关键事实时才追问一个问题。不要根据语气、身份或疾病做推断。"""


def _extract_json(content: str) -> dict:
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
    return json.loads(content)


async def interpret(text: str) -> InterpretResponse:
    rule_result = interpret_with_rules(text)
    # Explicit high-risk language is never delegated to a generative model.
    if rule_result.state.risk_level == RiskLevel.urgent:
        return rule_result

    api_key = os.getenv("LLM_API_KEY") or os.getenv("api_key")
    if not api_key:
        return rule_result

    base_url = (os.getenv("LLM_BASE_URL") or os.getenv("base_url") or "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("LLM_MODEL") or os.getenv("model") or "gpt-4o-mini"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": text},
                    ],
                },
            )
            response.raise_for_status()
            payload = _extract_json(response.json()["choices"][0]["message"]["content"])
            state = NeedState.model_validate(payload)
            if rule_result.state.risk_level == RiskLevel.elevated and state.risk_level == RiskLevel.ordinary:
                state.risk_level = RiskLevel.elevated
                state.risk_signals = rule_result.state.risk_signals
            return InterpretResponse(
                state=state,
                acknowledgement="我听见了。先不逼你解释清楚，我按你刚刚说的替你缩小范围。",
                source="model",
            )
    except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError, ValidationError):
        return rule_result
