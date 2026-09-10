from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re

import httpx
from pydantic import ValidationError

from .schemas import ClarifyOption, CorrectionOptions, InterpretResponse, NeedState, RiskLevel


logger = logging.getLogger("current.interpretation")

# 每次改 SYSTEM_PROMPT 都要抬版本号——留痕靠它才能对得上（FR-30）。
PROMPT_VERSION = "sp2-interpret-v0.4"

# 限流和 schema 失败是两回事，重试方式也不一样：
# 429/5xx 是「现在排不上队」，立刻重试等于白试，要等一下；
# schema 失败是「模型说了不合契约的话」，要立刻用 temperature=0 再要一次（FR-26）。
# 智谱免费档限的就是并发，不接这一条的话第一屏会经常悄悄退回规则版。
RATE_LIMIT_ATTEMPTS = 3
RATE_LIMIT_BACKOFF_SECONDS = 1.5


MOOD_RULES: dict[str, tuple[str, ...]] = {
    "quiet": ("安静", "太吵", "不想听", "别说话"),
    "noisy": ("脑子停不下来", "想太多", "一直想", "坐不住", "很乱"),
    "spark": ("灵感", "没方向", "想创作", "想看看"),
    "tired": ("很累", "没睡", "困", "疲惫", "躺不住"),
    "empty": ("空落落", "没着落", "空空", "没意思"),
    "tight": ("发紧", "绷着", "喘不过", "心慌"),
    "near": ("想有人", "陪我", "一个人难受", "有人在"),
    "fresh": ("换个地方", "待腻", "没见过", "出去看看"),
    "okay": ("还行", "挺好", "没事", "随便走走", "跳舞", "蹦迪", "想动", "出去嗨", "想玩"),
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
    "loud": ("吵一点", "热闹", "蹦迪", "跳舞", "嗨一点"),
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

# 诉求这一环：按「空间 / 刺激 / 恢复」各挑最常被说错的，凑够但不超过 6 个。
NEED_CORRECTIONS: tuple[str, ...] = ("hide", "sit", "walk", "green", "people", "slow", "new", "free")

# 约束这一环：key 用 "字段:值" 编码，前端照着改 NeedState，服务端仍会按
# NeedState 的字面量重新校验一次，客户端塞不进白名单以外的值。
CONSTRAINT_CORRECTIONS: tuple[tuple[str, str], ...] = (
    ("max_travel_minutes:15", "太远了，就近"),
    ("budget_level:free", "不想花钱"),
    ("environment:indoor", "想待在室内"),
    ("environment:outdoor", "想在户外"),
    ("social_mode:alone", "想一个人"),
    ("social_mode:with_people", "想周围有人"),
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
    elif _contains_any(text, ("有力气", "想运动", "想跳", "想跑", "跳舞", "蹦迪", "想动", "出去嗨")):
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
    """Quote the user's own words back. Never inferred, never stored, never logged.

    同一句话只引用一次。之前「不想见人」会先作为诉求出现、再作为社交约束出现，
    同一个信号说两遍，看起来像没读懂。
    """
    evidence: list[str] = []
    cited: set[str] = set()

    for token in _matched_tokens(text, MOOD_RULES.get(state.mood_id, ())):
        evidence.append(f"你说了「{token}」")
        cited.add(token)
        break

    for key in state.need_keys:
        tokens = [t for t in _matched_tokens(text, NEED_RULES.get(key, ())) if t not in cited]
        if not tokens:
            continue
        evidence.append(f"「{tokens[0]}」——我理解成{NEED_LABELS.get(key, key)}")
        cited.add(tokens[0])
        if len(evidence) >= 2:
            break

    if len(evidence) < 3:
        # 兜底那条也必须引用用户真说过的词，不能写死一句「你说了不想见人」。
        constraints: list[tuple[bool, tuple[str, ...], str]] = [
            (state.budget_level in {"free", "low"}, ("不花钱", "不想花钱", "不想花很多钱", "没钱", "免费", "便宜", "预算低", "少花点"), "所以我只找花不了什么钱的地方"),
            (state.social_mode == "alone", ("不想见人", "一个人", "别跟人说话", "躲"), "所以我把人多的地方去掉了"),
            (state.energy <= 1, ("没力气", "很累", "动不了", "不想动", "困", "疲惫"), "所以我把远的地方往后放了"),
        ]
        for applies, tokens, consequence in constraints:
            if not applies:
                continue
            fresh = [t for t in _matched_tokens(text, tokens) if t not in cited]
            if not fresh:
                continue
            evidence.append(f"「{fresh[0]}」——{consequence}")
            cited.add(fresh[0])
            break

    if not evidence:
        evidence.append("你说的话里我没抓到很明确的线索，所以这一条我不太确定")
    return evidence[:3]


def _already_holds(state: NeedState, encoded: str) -> bool:
    """已经是这个约束了就别再当成「纠错选项」摆出来。"""
    field, _, raw = encoded.partition(":")
    current = getattr(state, field, None)
    if field == "max_travel_minutes":
        return current is not None and current <= int(raw)
    return str(current) == raw


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


# 模型会把 prompt 里的字段名、占位符原样吐给用户。这些一出现就整条丢掉。
EVIDENCE_LEAKS = ("mood_id", "need_keys", "social_mode", "budget_level", "risk_level",
                  "所以我怎么理解", "json", "字段", "对应")


def _quotes_the_user(line: str, text: str) -> bool:
    """证据必须引用用户真说过的词，而且得是小在的口气。

    模型编一句听起来很懂的话是很容易的，所以逐条核对「」里的片段确实出现在
    原文里；再挡掉泄漏出来的字段名和过长的书面语（FR-28 代码侧护栏）。
    """
    if len(line) > 40 or any(leak in line.lower() for leak in EVIDENCE_LEAKS):
        return False
    quoted = re.findall(r"「([^」]{1,20})」", line)
    return bool(quoted) and all(q in text for q in quoted)


def _decorate(response: InterpretResponse, text: str, *, model_evidence: list[str] | None = None) -> InterpretResponse:
    state = response.state
    response.state_label = STATE_LABELS.get(state.mood_id, "说不太清楚")
    response.acknowledgement = _restatement(state)

    # 模型读懂了、规则没读懂的句子，证据也得跟着模型走——
    # 否则会出现「我猜你心里发紧」配「我没抓到明确线索」这种自相矛盾。
    verified: list[str] = []
    if model_evidence:
        verified = [
            line.strip() for line in model_evidence
            if isinstance(line, str) and line.strip() and _quotes_the_user(line, text)
        ][:3]
    response.evidence = verified or _evidence_for(text, state)
    # FR-03：四环都要能一步纠正，不能只让用户改「状态」这一环。
    # 地点那一环不给选项——「这几个都不想去」本身就是动作。
    response.corrections = CorrectionOptions(
        state=[
            ClarifyOption(key=key, label=label)
            for key, label in CORRECTION_CHIPS
            if key != state.mood_id
        ][:6],
        need=[
            ClarifyOption(key=key, label=NEED_LABELS[key])
            for key in NEED_CORRECTIONS
            if key not in state.need_keys
        ][:6],
        constraint=[
            ClarifyOption(key=key, label=label)
            for key, label in CONSTRAINT_CORRECTIONS
            if not _already_holds(state, key)
        ][:6],
    )

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
  "risk_signals": [],
  "evidence": ["1-3 条，见下面的写法"]
}
只有缺失会改变推荐的关键事实时才追问一个问题。不要根据语气、身份或疾病做推断。

evidence 的写法（这是给用户看的，不是给程序看的）：
- 每条必须包含用户真的说过的词，用「」括起来。编造用户没说过的话属于失败。
- 用小在的口气：短句、白话、身体感。不要出现字段名、术语、临床词。
- 每条不超过 25 个字。

好的例子：
  「吵完架」——所以我猜你现在还绷着
  「谁都不想理」——所以我把人多的地方去掉了
  「胃是空的」——所以我顺手找了能吃口东西的
不好的例子（不要这样写）：
  「加班到现在」——所以我怎么理解：当前处于长时间工作后的疲惫状态
  「人也是空的」——对应 mood_id 为 empty"""


def _extract_json(content: str) -> dict:
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
    return json.loads(content)


def _digest(text: str) -> str:
    """留痕只留摘要。原话不进日志——哈希能对上同一句话，但还原不出来（FR-30）。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _trace(*, outcome: str, text: str, attempt: int, model: str, detail: str = "") -> None:
    logger.info(
        json.dumps(
            {
                "event": "interpretation",
                "prompt_version": PROMPT_VERSION,
                "model": model,
                "attempt": attempt,
                "input_digest": _digest(text),
                "input_length": len(text),
                "outcome": outcome,
                "detail": detail,
            },
            ensure_ascii=False,
        )
    )


async def _call_model(client: httpx.AsyncClient, *, base_url: str, api_key: str, model: str, text: str, temperature: float) -> tuple[NeedState, list[str] | None]:
    payload = {
        "model": model,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    }
    # Qwen3 系列默认开思考链。我们这一步是受约束的信息抽取，不需要它推理，
    # 开着会从 5 秒变成 18 秒——直接吃掉 PRD §8 给的 3 秒预算。
    # 这个参数是 Qwen 专有的，别的厂商会拒收，所以按模型名判断。
    if "qwen3" in model.lower():
        payload["enable_thinking"] = False
    response = await client.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
    )
    response.raise_for_status()
    payload = _extract_json(response.json()["choices"][0]["message"]["content"])
    evidence = payload.pop("evidence", None)
    return NeedState.model_validate(payload), evidence


def _is_transient(error: Exception) -> bool:
    """值得等一下再试的：排队、服务端抖动、连接被重置。

    模型提供商说「你参数不对」不在此列——那种重试多少次都是一样的答案。
    """
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in (429, 500, 502, 503, 504)
    return isinstance(error, httpx.TransportError)


async def _call_model_with_backoff(client, *, base_url, api_key, model, text, temperature, attempt):
    """排队排不上就等一下再要一次。等不到就把异常抛出去，走上面的契约兜底。"""
    last: Exception | None = None
    for round_index in range(RATE_LIMIT_ATTEMPTS):
        try:
            return await _call_model(client, base_url=base_url, api_key=api_key, model=model, text=text, temperature=temperature)
        except Exception as error:  # noqa: BLE001 - 分流后原样抛出
            if not _is_transient(error):
                raise
            last = error
            _trace(outcome="transient_retry", text=text, attempt=attempt, model=model,
                   detail=f"{type(error).__name__} round {round_index + 1}/{RATE_LIMIT_ATTEMPTS}")
            if round_index + 1 < RATE_LIMIT_ATTEMPTS:
                await asyncio.sleep(RATE_LIMIT_BACKOFF_SECONDS * (round_index + 1))
    raise last  # type: ignore[misc]


async def interpret(text: str) -> InterpretResponse:
    rule_result = interpret_with_rules(text)
    # Explicit high-risk language is never delegated to a generative model.
    if rule_result.state.risk_level == RiskLevel.urgent:
        _trace(outcome="rules_safety_short_circuit", text=text, attempt=0, model="none")
        return _decorate(rule_result, text)

    api_key = os.getenv("LLM_API_KEY") or os.getenv("api_key")
    if not api_key:
        _trace(outcome="rules_no_model_configured", text=text, attempt=0, model="none")
        return _decorate(rule_result, text)

    base_url = (os.getenv("LLM_BASE_URL") or os.getenv("base_url") or "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("LLM_MODEL") or os.getenv("model") or "glm-4.7-flash"

    # 输出契约（FR-26）：校验失败以 temperature=0 重试一次，再失败走规则兜底，绝不空屏。
    async with httpx.AsyncClient(timeout=20) as client:
        for attempt, temperature in enumerate((0.1, 0.0), start=1):
            try:
                state, model_evidence = await _call_model_with_backoff(
                    client, base_url=base_url, api_key=api_key, model=model, text=text,
                    temperature=temperature, attempt=attempt,
                )
            except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError, ValidationError) as error:
                _trace(outcome="contract_failed", text=text, attempt=attempt, model=model, detail=type(error).__name__)
                continue

            # 代码侧护栏：模型不能把规则已经认定的风险降级（FR-28）。
            if rule_result.state.risk_level == RiskLevel.elevated and state.risk_level == RiskLevel.ordinary:
                state.risk_level = RiskLevel.elevated
                state.risk_signals = rule_result.state.risk_signals
            _trace(outcome="model_ok", text=text, attempt=attempt, model=model)
            return _decorate(
                InterpretResponse(
                    state=state,
                    acknowledgement="我听见了。先不逼你解释清楚，我按你刚刚说的替你缩小范围。",
                    source="model",
                ),
                text,
                model_evidence=model_evidence,
            )

    _trace(outcome="rules_fallback_after_retry", text=text, attempt=2, model=model)
    return _decorate(rule_result, text)
