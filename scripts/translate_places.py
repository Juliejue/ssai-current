"""把 26 个人工地点译成英文，产出 backend_app/data/places.en.json。

为什么要单独一份而不是现场翻：
- 现场翻要多一次模型往返，用户就在那儿等着；
- 这些文案是这个产品的门面（「让店员放给你听」「绕着水走一圈，不用绕完」），
  值得先译好、人能过一遍，而不是每次重新掷一次骰子。

译的标准和中文一条线：小在说话是短句、白话、身体感。
不诊断、不评判、不承诺效果，也不要译成旅游宣传腔。

    .venv/bin/python -m scripts.translate_places
    .venv/bin/python -m scripts.translate_places --only postpost soloist
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import re
import sys

import httpx


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend_app" / "data" / "places.json"
OVERRIDES = ROOT / "backend_app" / "data" / "place_overrides.json"
TARGET = ROOT / "backend_app" / "data" / "places.en.json"

FIELDS = ("placeName", "action", "category", "see", "cost", "suggestedDuration", "transport")

SYSTEM = """You translate a Chinese emotional-wellbeing app's place cards into English.

This is not tourist copy. The voice is a quiet friend who knows the city:
short, plain, physical. Never lyrical, never promotional, never clinical.

Rules:
- "action" is something the person DOES there. Keep it a move, not a verdict.
  「让店员放给你听」 -> "Ask them to play one for you"  (not "Enjoy vinyl records")
- "placeName": keep an existing official English name if the place plainly has one
  (postpost, soloist, fRUITYSHOP). Otherwise transliterate in pinyin and, where a
  short gloss genuinely helps, add it: 什刹海 -> "Shichahai". Do not invent English names.
- "category" is a short tag like "record shop · indoors", lowercase.
- "cost"/"see"/"transport"/"suggestedDuration": plain, factual, same length ballpark.
- "matchReason" values: one sentence each, the reason this place fits that state.
  Never promise it will help. Never diagnose.
- "placeInsights": a list of {t, d}. "t" is a short noticing (3-5 words), "d" one plain sentence.
- "environmentTags": short lowercase tags, 1-4 words each.
- Keep any number, price, or line name exactly as it is.

Output JSON only, same keys as the input object."""


def _extract(content: str) -> dict:
    return json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE))


async def translate(client: httpx.AsyncClient, base: str, key: str, model: str, place: dict) -> dict | None:
    payload = {field: place.get(field) for field in FIELDS if place.get(field)}
    payload["matchReason"] = place.get("matchReason") or {}
    # 详情页上「小在眼中的这里」和标签也要译，否则切了英文那一屏还有一半中文。
    payload["placeInsights"] = place.get("placeInsights") or []
    payload["environmentTags"] = place.get("environmentTags") or []
    body = {
        "model": model,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=1)},
        ],
    }
    if "qwen3" in model.lower():
        body["enable_thinking"] = False
    for attempt in range(1, 5):
        try:
            response = await client.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json=body,
            )
            response.raise_for_status()
            return _extract(response.json()["choices"][0]["message"]["content"])
        except (httpx.HTTPError, KeyError, IndexError, ValueError):
            await asyncio.sleep(0.6 * attempt)
    return None


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", default=None)
    args = parser.parse_args()

    key = os.getenv("LLM_API_KEY")
    if not key:
        print("没有 LLM_API_KEY。先 `set -a && . ./.env && set +a`。")
        return 1
    base = (os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("LLM_MODEL") or "qwen3.8-flash"

    catalog = json.loads(SOURCE.read_text(encoding="utf-8"))
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8")).get("places", {})
    places = []
    for place in catalog["PLACES"]:
        merged = dict(place)
        merged.update(overrides.get(place["placeId"], {}))
        places.append(merged)
    if args.only:
        places = [p for p in places if p["placeId"] in set(args.only)]

    existing = json.loads(TARGET.read_text(encoding="utf-8")) if TARGET.exists() else {"places": {}}
    out: dict = existing.get("places", {})

    async with httpx.AsyncClient(timeout=60) as client:
        semaphore = asyncio.Semaphore(3)

        async def one(place: dict) -> tuple[str, dict | None]:
            async with semaphore:
                return place["placeId"], await translate(client, base, key, model, place)

        results = await asyncio.gather(*(one(p) for p in places))

    ok = 0
    for place_id, translated in results:
        if translated:
            ok += 1
            out[place_id] = translated
            print(f"  {place_id:<16} {translated.get('placeName','')} — {translated.get('action','')}")
        else:
            print(f"  {place_id:<16} 失败（保留旧的，如果有）")

    TARGET.write_text(json.dumps({"places": out}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{ok}/{len(places)} 译好，写入 {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
