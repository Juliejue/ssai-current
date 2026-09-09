from __future__ import annotations

import json
import os
import re

import httpx
from pydantic import ValidationError

from .schemas import ClarifyOption, InterpretResponse, NeedState, RiskLevel


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
    "free": ("不花钱", "不想花钱", "不想花很多钱", "没钱", "便宜", "预算低", "少花点"),
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

# Body-level wording only. No clinical or personality labels ever leave this file.
STATE_LABELS: dict[str, str] = {
    "low": "没什么力气",
    "quiet": "需要安静",
    "noisy": "脑子停不下来",
    "spark": "想要点灵感",
    "tired": "累但静不下来",
    "empty": "空落落的",
    "tight": "心里发紧",
    "near": "想有人在旁边",
    "fresh": "想换个地方",
    "okay": "状态还行",
}

NEED_LABELS: dict[str, str] = {
    "hide": "不被人看见",
    "sit": "能坐很久",
    "walk": "能一直走",
    "free": "不用花太多钱",
    "green": "想看见绿色",
    "new": "想看没见过的",
    "sound": "想听点声音",
    "people": "周围有人就行",
    "loud": "想要吵一点",
    "slow": "想慢下来",
    "hands": "想手上有事做",
    "breathe": "想喘口气",
    "nothing": "什么都不想决定",
}

# The six body-feeling chips offered when the user says "不太对" (FR-03 / US-02).
CORRECTION_CHIPS: tuple[tuple[str, str], ...] = (
    ("tight", "心里发紧"),
    ("noisy", "脑子停不下来"),
    ("tired", "累但静不下来"),
    ("empty", "空落落的"),
    ("near", "想有人在旁边"),
    ("fresh", "想换个地方"),
    ("quiet", "需要安静"),
    ("low", "没什么力气"),
)

CLARIFY_QUESTIONS: dict[str, tuple[str, tuple[tuple[str, str], ...]]] = {
    "social_mode": (
        "只问一句：现在想一个人待着，还是周围有人、但不用说话？",
        (("alone", "想一个人"), ("low_contact", "有人但不说话"), ("either", "都行")),
    ),
    "max_travel_minutes": (
        "只问一句：现在最多愿意在路上花多久？",
        (("10", "10 分钟内"), ("25", "20 分钟左右"), ("60", "远一点也行")),
    ),
    "budget_level": (
        "只问一句：今天想不想花钱？",
        (("free", "不想花钱"), ("low", "花一点可以"), ("unknown", "都行")),
    ),
}


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

    budget = "free" if _contains_any(text, ("不花钱", "不想花钱", "没钱", "免费")) else "low" if _contains_any(text, ("便宜", "不想花很多钱", "预算低", "少花点")) else "unknown"
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


def _matched_tokens(text: str, patterns: tuple[str, ...]) -> list[str]:
    return [token for token in patterns if token in text]


def _evidence_for(text: str, state: NeedState) -> list[str]:
    """Quote the user's own words back. Never inferred, never stored, never logged."""
    evidence: list[str] = []
    for token in _matched_tokens(text, MOOD_RULES.get(state.mood_id, ())):
        evidence.append(f"你说了「{token}」")
        break
    for key in state.need_keys:
        tokens = _matched_tokens(text, NEED_RULES.get(key, ()))
        if tokens:
            evidence.append(f"「{tokens[0]}」——我理解成{NEED_LABELS.get(key, key)}")
        if len(evidence) >= 2:
            break
    if len(evidence) < 3:
        if state.budget_level == "free":
            evidence.append("你提到了钱，所以我只找不用消费的地方")
        elif state.social_mode == "alone":
            evidence.append("你说了不想见人，所以我把人多的地方去掉了")
        elif state.energy <= 1:
            evidence.append("听起来你没什么力气，所以我把远的地方往后放了")
    if not evidence:
        evidence.append("你说的话里我没抓到很明确的线索，所以这一条我不太确定")
    return evidence[:3]


def _needs_clarification(state: NeedState) -> str | None:
    """Ask at most one question, and only when the answer changes the shortlist."""
    if state.social_mode == "either" and len(state.need_keys) < 2:
        return "social_mode"
    if state.energy <= 1 and state.max_travel_minutes is None:
        return "max_travel_minutes"
    if state.budget_level == "unknown" and "free" not in state.need_keys and state.confidence < 0.5:
        return "budget_level"
    return None


def _restatement(state: NeedState) -> str:
    label = STATE_LABELS.get(state.mood_id, "说不太清楚")
    needs = [NEED_LABELS[key] for key in state.need_keys if key in NEED_LABELS][:2]
    tail = "，需要一个" + "、".join(needs) + "的地方" if needs else ""
    return f"我猜你现在更接近「{label}」{tail}。猜错了就说一声，我马上换。"


def _decorate(response: InterpretResponse, text: str) -> InterpretResponse:
    state = response.state
    response.state_label = STATE_LABELS.get(state.mood_id, "说不太清楚")
    response.acknowledgement = _restatement(state)
    response.evidence = _evidence_for(text, state)
    response.correction_chips = [
        ClarifyOption(key=key, label=label)
        for key, label in CORRECTION_CHIPS
        if key != state.mood_id
    ][:6]

    field = None if state.risk_level is not RiskLevel.ordinary else _needs_clarification(state)
    if field and field in CLARIFY_QUESTIONS:
        question, options = CLARIFY_QUESTIONS[field]
        state.needs_clarification = True
        state.clarifying_question = question
        response.clarify_field = field
        response.clarify_options = [ClarifyOption(key=key, label=label) for key, label in options]
    else:
        state.needs_clarification = False
        state.clarifying_question = None
    return response


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
        return _decorate(rule_result, text)

    api_key = os.getenv("LLM_API_KEY") or os.getenv("api_key")
    if not api_key:
        return _decorate(rule_result, text)

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
            return _decorate(
                InterpretResponse(
                    state=state,
                    acknowledgement="我听见了。先不逼你解释清楚，我按你刚刚说的替你缩小范围。",
                    source="model",
                ),
                text,
            )
    except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError, ValidationError):
        # Contract failure never reaches the user as a blank screen (FR-26).
        return _decorate(rule_result, text)
