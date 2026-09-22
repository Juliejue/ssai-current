"""给现场搜出来的地点写一句话（FR-16 的后半段）。

这是「情绪空间」和大众点评的分界线。

同样是「陈独秀旧居，距你 640 米」，大众点评给你营业时间和评分；
我们要给的是——**你此刻这个状态，为什么是这里**。
类别模板写不出这句话：它只知道「故居这一类通常安静」，
不知道「陈独秀」这三个字本身带着什么。模型知道。

但模型也最容易在这里撒谎：它会顺口编出「这里有一面很好的墙」。
所以规则只有一条，而且是硬的——**只许用地名和类别里已有的信息**。
写不出来就退回模板，绝不编。

排序仍然不交给模型（守则 7）。它只负责把已经排好的地点说成人话。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

import httpx

from .schemas import NeedState


logger = logging.getLogger("current.narrate")

# 和 tests/test_redline.py 同一份 §5.2 词表。模型写出这些词，整条丢掉。
BANNED_WORDS: tuple[str, ...] = (
    "焦虑症", "抑郁症", "抑郁", "躁郁", "强迫症", "创伤后",
    "高敏感", "你太敏感", "人格", "病理", "确诊", "疗效", "治愈",
    "你应该", "别想太多", "想开点", "振作起来",
)

# 守则 6：不承诺效果。一个地方能不能接住你，只有你去了才知道。
PROMISE_WORDS: tuple[str, ...] = (
    "一定会", "保证", "肯定能", "让你好起来", "会变好", "药", "疗", "解决你的",
)

MAX_ACTION_CHARS = 16
MAX_WHY_CHARS = 34
# 英文一个词就占好几个字符，按汉字的尺子量会把好句子全砍掉。
MAX_ACTION_CHARS_EN = 44
MAX_WHY_CHARS_EN = 84
NARRATE_TIMEOUT_SECONDS = 12
NARRATE_ATTEMPTS = 3
NARRATE_PROMPT_VERSION = "narrate-v0.4-compact"

SYSTEM_PROMPT = """你是小在。按“此刻状态 + 地点名 + 类别”为每个地点写两句，只输出：
{"places":[{"id":"...","action":"...","why_now":"..."}]}
action=到那儿能做的一件具体事，≤16字；why_now=为何是此刻的这里，≤34字。
只能使用地点名和类别已经透露的信息；不得编内部环境、设施、评价、营业或效果。
不诊断、不评判、不承诺变好；短、白话、有动作，不抒情，不出现字段名/类别名/术语。
好：陈独秀旧居→action“在别人住过的院子里坐一会儿”。
坏：感受历史厚重；这里环境优雅；缓解你的焦虑。"""


SYSTEM_PROMPT_EN = """You are Xiaozai. From current state + place name + category, write two lines per place. JSON only:
{"places":[{"id":"...","action":"...","why_now":"..."}]}
action: one concrete move, <=40 chars. why_now: why here now, <=80 chars.
Use only facts revealed by name/category. Never invent interiors, facilities, reviews, hours, or outcomes.
No diagnosis, judgement, promises, jargon, category/field names, lyrical copy, or slogans."""


def _clean(line: Any, limit: int) -> str | None:
    if not isinstance(line, str):
        return None
    text = re.sub(r"\s+", " ", line).strip().strip("。.，,")
    if not text or len(text) > limit:
        return None
    lowered = text.lower()
    if any(word in text for word in BANNED_WORDS):
        return None
    if any(word.lower() in lowered for word in PROMISE_WORDS):
        return None
    # 「」里的东西是我们引用用户原话的格式，模型不该自己造。
    if "「" in text or "{" in text or "_id" in lowered:
        return None
    return text


def _state_line(state: NeedState, lang: str = "zh") -> str:
    from .i18n import AVOID_LABELS_EN, NEED_LABELS_EN, PLACE_TYPE_LABELS_EN, STATE_LABELS_EN
    from .interpretation import AVOID_LABELS, NEED_LABELS, PLACE_TYPE_LABELS, STATE_LABELS

    english = lang == "en"
    states = STATE_LABELS_EN if english else STATE_LABELS
    needs = NEED_LABELS_EN if english else NEED_LABELS
    avoids = AVOID_LABELS_EN if english else AVOID_LABELS
    place_types = PLACE_TYPE_LABELS_EN if english else PLACE_TYPE_LABELS
    # 明确活动放在状态前面，避免文案模型再次把「想吃烤串」抽象成“需要安静”。
    parts = [place_types[key] for key in state.place_types if key in place_types][:2]
    parts += [states.get(state.mood_id, "hard to name" if english else "说不太清楚")]
    parts += [needs[key] for key in state.need_keys if key in needs][:2]
    parts += [avoids[key] for key in state.avoid_tags if key in avoids][:1]
    return (", " if english else "、").join(parts)


async def narrate(places: list[dict], state: NeedState, lang: str = "zh") -> dict[str, dict[str, str]]:
    """返回 {placeId: {"action":…, "why_now":…}}。任何一步出问题都返回空——调用方退回模板。"""
    api_key = os.getenv("LLM_API_KEY") or os.getenv("api_key")
    if not api_key or not places:
        return {}

    base_url = (os.getenv("LLM_BASE_URL") or os.getenv("base_url") or "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("LLM_MODEL") or os.getenv("model") or "glm-4.7-flash"
    listing = "\n".join(
        (
            f'- id={place["placeId"]}  name="{place["placeName"]}"  category={place.get("category_en") or place["category"]}'
            if lang == "en"
            else f'- id={place["placeId"]}  名字「{place["placeName"]}」  类别 {place["category"]}'
        )
        for place in places
    )
    user_prompt = (f"Right now: {_state_line(state, lang)}\n\nPlaces:\n{listing}" if lang == "en"
                   else f"此刻的状态：{_state_line(state)}\n\n地点：\n{listing}")

    body: dict[str, Any] = {
        "model": model,
        "temperature": 0.7,  # 这是写文案，不是抽结构，可以松一点
        "max_tokens": max(160, min(480, len(places) * 110)),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT_EN if lang == "en" else SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }
    # Qwen3 不发这个参数要 18 秒，发了 5 秒（见交接文档 §3②）。
    if "qwen3" in model.lower():
        body["enable_thinking"] = False

    # 开发机和线上都在境外，调这个模型是跨境的，ConnectError 是常态不是异常
    # （见交接文档 §3①）。不重试的话，用户拿到的就是一句模板套话。
    payload: dict[str, Any] | None = None
    for attempt in range(1, NARRATE_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=NARRATE_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=body,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
            payload = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE))
            break
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as error:
            logger.info(json.dumps({
                "event": "narrate", "prompt_version": NARRATE_PROMPT_VERSION,
                "outcome": "retry" if attempt < NARRATE_ATTEMPTS else "failed",
                "attempt": attempt, "detail": type(error).__name__,
            }))
            if attempt < NARRATE_ATTEMPTS:
                await asyncio.sleep(0.4 * attempt)
    if payload is None:
        return {}

    written: dict[str, dict[str, str]] = {}
    for item in payload.get("places") or []:
        if not isinstance(item, dict):
            continue
        place_id = str(item.get("id") or "")
        action = _clean(item.get("action"), MAX_ACTION_CHARS_EN if lang == "en" else MAX_ACTION_CHARS)
        why_now = _clean(item.get("why_now"), MAX_WHY_CHARS_EN if lang == "en" else MAX_WHY_CHARS)
        # 两句缺一条就整条不要：半句模板半句模型，读起来会精神分裂。
        if place_id and action and why_now:
            written[place_id] = {"action": action, "why_now": why_now}
    logger.info(json.dumps({"event": "narrate", "prompt_version": NARRATE_PROMPT_VERSION,
                            "outcome": "ok", "asked": len(places), "kept": len(written)}))
    return written


async def narrate_quietly(places: list[dict], state: NeedState, lang: str = "zh") -> dict[str, dict[str, str]]:
    """narrate 的免死金牌版：无论出什么事都不让推荐这条主路径失败。"""
    try:
        return await narrate(places, state, lang)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - 文案是锦上添花，不能拖垮推荐
        logger.exception("narrate crashed")
        return {}
