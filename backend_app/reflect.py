"""把离开之后的一句话，变成这次到访的结构化反馈（FR-10）。

原来这一步是两道选择题：先在 −3…+3 里点一个，再从一堆标签里勾。
填表当然能拿到干净的数据，但它跟这个产品的其余部分是两种东西——
前面用户只要说一句话就行，到了这里突然变成问卷。

现在：他说一句话（或者打一行字），模型把它变成分数和因素，
小在再用人话确认一遍。改，还是在同一句话里改。

**选择题那条路没有删。** 语音会坏、有人就是不想说话、模型也会失败——
任何一种情况下，「自己选」都还在那儿。

护栏和理解那一步是同一套：
- 因素只能从这个地点自己的选项里挑，模型编的词一律丢掉
- 分数夹在 −3…+3
- 不诊断、不评判、不承诺效果
- 小在那句话必须是对用户说的话的回应，不能编这个地方的事实
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any
from urllib.parse import urlsplit

import httpx

from .narrate import BANNED_WORDS, PROMISE_WORDS
from .security import checked_model_base_url


logger = logging.getLogger("current.reflect")

REFLECT_TIMEOUT_SECONDS = 10
REFLECT_ATTEMPTS = 2
REFLECT_MAX_TOKENS = 480
MAX_ACK_CHARS = 46
MAX_ACK_CHARS_EN = 110

# 哪一环最对（FR-10b）。和前端那组按钮同一套值。
STAGES = ("none", "state", "need", "constraint", "place")

SYSTEM_PROMPT = """你是「小在」。用户刚从一个地方离开，说了一句话描述这趟怎么样。
把它变成 JSON，并且用一句话回应他。
输入可能包含前面几轮用户与小在的对话。回应最后一轮，记住前文，不重复已问过的问题。
用户继续聊天或提问时也要自然回应；不足以判断变化时 change_score 可为 null，不强行评分。

只输出 JSON：
{
  "change_score": -3 到 3 的整数或 null,
  "factors": ["只能从我给你的选项原文里挑，最多 3 个"],
  "mismatch_stage": "none|state|need|constraint|place",
  "acknowledgement": "小在对他说的一句话，不超过 46 字"
}

change_score 是「他自己出发前和现在的差」，不是给这个地方打分。
  明显更难受 −3，差不多 0，明显变好 +3。他没说清楚前后变化就给 null；喜欢夕阳不代表心情改善。

factors 必须逐字来自我给的选项列表。他提到的事情如果列表里没有，就不要放。

mismatch_stage 只在他明显表达了「哪一步不对」时才填：
  state=状态猜错了，need=需求找错了，constraint=远近或花销不合适，place=地方不对。
  看不出来就 none。

acknowledgement 的写法：
- 是回应，不是复述。他说了什么，你接住什么。
- 用小在的口气：短句、白话、身体感。不抒情、不总结陈词。
- 不诊断、不评判、不承诺「下次一定」。
- 只说他说过的事。不许编这个地方的细节。
- 不好的时候不要安慰过头，「这次没接住」就够了。

好的例子：
  他说「在河边坐了半小时，风挺舒服，就是人有点多」
  → "风和能坐下这两样起作用了。人多那条我记下来了。"
  他说「没什么感觉，可能今天就是不行」
  → "那就不是地方的问题。今天先这样，不用交代什么。"
不好的例子：
  "很高兴你感觉好多了！继续保持！"   （夸张、承诺、感叹号）
  "您的情绪状态有所改善"             （书面语、像诊断）"""

ENGLISH_SUFFIX = """

This user reads English. Write `acknowledgement` in English, under 110 characters.
Same voice: short, plain, physical. Not cheerful, not clinical, no exclamation marks.
`factors` still must come verbatim from the option list I give you (they may be Chinese)."""


def _clean_ack(line: Any, limit: int) -> str | None:
    if not isinstance(line, str):
        return None
    text = re.sub(r"\s+", " ", line).strip()
    if not text or len(text) > limit:
        return None
    lowered = text.lower()
    if any(word in text for word in BANNED_WORDS):
        return None
    if any(word.lower() in lowered for word in PROMISE_WORDS):
        return None
    return text


def _fallback(options: list[str], failure_code: str = "provider_error") -> dict[str, Any]:
    """模型没接住的时候。分数留空，让前端退回自己选——绝不替用户猜一个分数。"""
    return {"change_score": None, "factors": [], "mismatch_stage": "none", "acknowledgement": None, "status": "unavailable", "failure_code": failure_code}


async def reflect(
    text: str,
    *,
    place_name: str,
    pre_mood: str,
    options: list[str],
    lang: str = "zh",
) -> dict[str, Any]:
    api_key = os.getenv("LLM_API_KEY") or os.getenv("api_key")
    if not api_key:
        return _fallback(options, "configuration_missing")
    if not text.strip():
        return _fallback(options, "invalid_response")

    base_url = checked_model_base_url(os.getenv("LLM_BASE_URL") or os.getenv("base_url"))
    if not base_url:
        result = _fallback(options, "configuration_invalid")
        try:
            result["failure_host"] = urlsplit(os.getenv("LLM_BASE_URL") or os.getenv("base_url") or "").hostname
        except ValueError:
            pass
        return result
    model = os.getenv("LLM_MODEL") or os.getenv("model") or "glm-4.7-flash"

    user_prompt = (
        f"他去的地方：{place_name}\n"
        f"出发前的状态：{pre_mood}\n"
        f"可选的因素（只能从这里挑，逐字照抄）：{'、'.join(options)}\n\n"
        f"他说：{text.strip()}"
    )
    body: dict[str, Any] = {
        "model": model,
        "temperature": 0.4,
        "max_tokens": REFLECT_MAX_TOKENS,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT + (ENGLISH_SUFFIX if lang == "en" else "")},
            {"role": "user", "content": user_prompt},
        ],
    }
    if "qwen3" in model.lower():
        body["enable_thinking"] = False
    elif model.lower().startswith("glm-4.7"):
        body["thinking"] = {"type": "disabled"}

    payload: dict[str, Any] | None = None
    failure_code = "provider_error"
    for attempt in range(1, REFLECT_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=REFLECT_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=body,
                )
                response.raise_for_status()
                choice = response.json()["choices"][0]
                content = choice["message"].get("content")
                if choice.get("finish_reason") == "length":
                    raise ValueError("truncated_response")
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("empty_content")
            payload = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE))
            if not isinstance(payload, dict):
                raise ValueError("invalid_json_shape")
            if not _clean_ack(payload.get("acknowledgement"), MAX_ACK_CHARS_EN if lang == "en" else MAX_ACK_CHARS):
                raise ValueError("invalid_acknowledgement")
            break
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as error:
            payload = None
            failure_code = "provider_error" if isinstance(error, httpx.HTTPError) else "invalid_response"
            logger.info(json.dumps({
                "event": "reflect", "outcome": "retry" if attempt < REFLECT_ATTEMPTS else "failed",
                "attempt": attempt, "detail": type(error).__name__,
                "model": model,
                "reason": str(error) if isinstance(error, ValueError) else "provider_request_failed",
            }))
            if attempt < REFLECT_ATTEMPTS:
                await asyncio.sleep(0.4 * attempt)
    if payload is None:
        return _fallback(options, failure_code)

    # 代码侧护栏：模型给什么都得先过这一关。
    try:
        score = int(payload.get("change_score"))
        score = max(-3, min(3, score))
    except (TypeError, ValueError):
        score = None

    allowed = {option: option for option in options}
    factors = [allowed[f] for f in (payload.get("factors") or []) if isinstance(f, str) and f in allowed][:3]

    stage = payload.get("mismatch_stage")
    stage = stage if stage in STAGES else "none"

    ack = _clean_ack(payload.get("acknowledgement"), MAX_ACK_CHARS_EN if lang == "en" else MAX_ACK_CHARS)

    logger.info(json.dumps({
        "event": "reflect", "outcome": "ok",
        "has_score": score is not None, "factor_count": len(factors), "stage": stage,
    }))
    return {"change_score": score, "factors": factors, "mismatch_stage": stage, "acknowledgement": ack, "status": "ok"}


async def reflect_quietly(text: str, **kwargs: Any) -> dict[str, Any]:
    try:
        return await reflect(text, **kwargs)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - 这一步失败就退回选择题，不能把闭环卡死
        logger.exception("reflect crashed")
        return _fallback(kwargs.get("options") or [])
