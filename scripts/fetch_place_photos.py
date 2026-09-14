"""给人工核对过的地点补上高德的真实照片。

原型里 26 个地点用的是生成符号（sigil），当初的理由写在 HTML 注释里：
「6+ 个地点无法拿到稳定合规的匹配图源，错配图片比抽象符号更糟」。
那个判断在当时是对的——但前提变了：这些地点现在都有人工核对过的高德 POI ID，
按 ID 取回来的照片就是这一家，不存在错配。

只处理 verification_status == "verified" 的。没核对过身份的地点仍然不配图：
那才是当初那条理由真正针对的情况。

    .venv/bin/python -m scripts.fetch_place_photos          # 写入 place_overrides.json
    .venv/bin/python -m scripts.fetch_place_photos --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys

import httpx


ROOT = pathlib.Path(__file__).resolve().parents[1]
OVERRIDES = ROOT / "backend_app" / "data" / "place_overrides.json"
AMAP_DETAIL = "https://restapi.amap.com/v5/place/detail"
ATTEMPTS = 4


async def photos_for(client: httpx.AsyncClient, key: str, poi_id: str) -> list[str]:
    for attempt in range(1, ATTEMPTS + 1):
        try:
            response = await client.get(
                AMAP_DETAIL,
                params={"key": key, "id": poi_id, "show_fields": "photos"},
            )
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            # 跨境调用会偶发失败，这不是数据问题（见交接文档 §3①）。
            await asyncio.sleep(0.6 * attempt)
            continue
        if str(payload.get("status")) != "1":
            return []
        urls: list[str] = []
        for poi in payload.get("pois") or []:
            for photo in poi.get("photos") or []:
                url = str((photo or {}).get("url") or "").strip()
                if url.startswith("http://"):
                    url = "https://" + url[len("http://"):]
                if url.startswith("https://") and url not in urls:
                    urls.append(url)
        return urls[:3]
    return []


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    key = os.getenv("AMAP_WEB_SERVICE_KEY")
    if not key:
        print("没有 AMAP_WEB_SERVICE_KEY。先 `set -a && . ./.env && set +a`。")
        return 1

    data = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    places: dict = data.get("places", {})
    targets = {
        place_id: entry["amap"]["provider_place_id"]
        for place_id, entry in places.items()
        if (entry.get("amap") or {}).get("verification_status") == "verified"
        and (entry.get("amap") or {}).get("provider_place_id")
    }
    print(f"人工核对过的地点：{len(targets)} 个")

    async with httpx.AsyncClient(timeout=25) as client:
        semaphore = asyncio.Semaphore(4)

        async def one(place_id: str, poi_id: str) -> tuple[str, list[str]]:
            async with semaphore:
                return place_id, await photos_for(client, key, poi_id)

        results = await asyncio.gather(*(one(pid, poi) for pid, poi in targets.items()))

    got = 0
    for place_id, urls in sorted(results):
        if urls:
            got += 1
            places[place_id]["photos"] = urls
        print(f"  {place_id:<16} {len(urls)} 张")

    print(f"\n拿到照片的：{got}/{len(targets)}")
    if args.dry_run:
        print("--dry-run，没有写入。")
        return 0
    data["places"] = places
    OVERRIDES.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已写入 {OVERRIDES.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
