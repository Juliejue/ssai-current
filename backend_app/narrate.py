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

SYSTEM_PROMPT = """你是「小在」，一个帮人找地方待着的声音。
给你一个人此刻的状态，和几个地点的名字与类别，为每个地点写两句话。

只输出 JSON：{"places":[{"id":"...","action":"...","why_now":"..."}]}

action：到了那儿具体能做的一件事。不超过 16 字，要有画面，是动作不是评价。
why_now：为什么是此刻的这里。不超过 34 字，从心理环境出发。

铁规则（违反就是这条作废）：
1. 只许用地名和类别里已经有的信息。你不知道这个地方里面长什么样，
   不许编「有一面墙」「有很好的音响」「靠窗的位置」这类具体事实。
   地名本身透露的除外——「陈独秀旧居」你可以用「有人在这儿住过」。
2. 不诊断、不贴标签、不评判。不出现临床词，也不说「你太敏感」这类话。
3. 不承诺效果。不说「会让你好起来」。最多说「可能」「也许」。
4. 用小在的口气：短句、白话、身体感。不抒情，不排比，不喊口号。
5. 不许出现字段名、类别名、术语。

好的例子：
  地点「陈独秀旧居 · 故居」，状态「累但静不下来、不想见人」
  action: 在别人住过的院子里坐一会儿
  why_now: 这里的时间是别人的，你不用管自己的
  地点「中山公园音乐堂 · 剧场」，状态「脑子停不下来」
  action: 看看今晚有没有场次
  why_now: 有人在台上，你的注意力就有地方放
不好的例子（不要这样）：
  action: 感受历史的厚重      （空话，没有动作）
  why_now: 这里环境优雅安静，适合放松心情   （编了你不知道的事实）
  why_now: 缓解你的焦虑情绪   （诊断 + 承诺效果）"""


SYSTEM_PROMPT_EN = """You are Xiaozai, a voice that helps someone find a place to be right now.
Given how a person feels and a few places (name + category), write two lines for each.

Output JSON only: {"places":[{"id":"...","action":"...","why_now":"..."}]}

action: one concrete thing they can do there. Under 40 characters. A move, not a verdict.
why_now: why here, right now. Under 80 characters. Start from the psychological environment.

Hard rules (break one and the line is discarded):
1. Use ONLY what the name and category already tell you. You have not been inside.
   Never invent specifics like "a good wall", "great speakers", "a seat by the window".
   What the name itself reveals is fair game.
2. No diagnosing, labelling, or judging. No clinical words. Never "you're too sensitive".
3. Never promise an outcome. Not "this will make you feel better". "Might" at most.
4. Xiaozai's voice: short, plain, physical. Not lyrical, no slogans.
5. No field names, category names, or jargon.

Good:
  Place "Nanchizi Art Museum · gallery", state "tired but wired, no people"
  action: Stand in a corner and look at one painting
  why_now: Nobody in a gallery expects anything from you
Bad:
  action: Soak in the rich atmosphere      (empty, no action)
  why_now: A quiet elegant spot perfect for relaxing   (invented facts)
  why_now: Eases your anxiety              (diagnosis + promise)"""


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
    from .i18n import AVOID_LABELS_EN, NEED_LABELS_EN, STATE_LABELS_EN
    from .interpretation import AVOID_LABELS, NEED_LABELS, STATE_LABELS

    english = lang == "en"
    states = STATE_LABELS_EN if english else STATE_LABELS
    needs = NEED_LABELS_EN if english else NEED_LABELS
    avoids = AVOID_LABELS_EN if english else AVOID_LABELS
    parts = [states.get(state.mood_id, "hard to name" if english else "说不太清楚")]
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
        f'- id={place["placeId"]}  名字「{place["placeName"]}」  类别 {place["category"]}'
        for place in places
    )
    user_prompt = (f"Right now: {_state_line(state, lang)}\n\nPlaces:\n{listing}" if lang == "en"
                   else f"此刻的状态：{_state_line(state)}\n\n地点：\n{listing}")

    body: dict[str, Any] = {
        "model": model,
        "temperature": 0.7,  # 这是写文案，不是抽结构，可以松一点
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
                "event": "narrate", "outcome": "retry" if attempt < NARRATE_ATTEMPTS else "failed",
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
    logger.info(json.dumps({"event": "narrate", "outcome": "ok", "asked": len(places), "kept": len(written)}))
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
