from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from backend_app.map_provider import AmapClient, MapProviderError
from backend_app.recommender import load_catalog


DEFAULT_OUTPUT = Path(__file__).parents[1] / "backend_app" / "data" / "amap_candidates.json"


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="为 Current 地点生成高德候选；不会自动修改正式地点数据。"
    )
    parser.add_argument("--place-id", help="只核对一个 Current place ID")
    parser.add_argument("--region", default="北京市")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if not os.getenv("AMAP_WEB_SERVICE_KEY"):
        raise SystemExit("AMAP_WEB_SERVICE_KEY is required")

    places = load_catalog()["PLACES"]
    if args.place_id:
        places = [place for place in places if place["placeId"] == args.place_id]
        if not places:
            raise SystemExit(f"unknown place ID: {args.place_id}")

    client = AmapClient()
    resolved: dict[str, object] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "region": args.region,
        "instructions": "人工核对名称、地址和坐标后，再复制唯一正确项到 place_overrides.json。不要按排名自动采用。",
        "places": {},
    }
    for place in places:
        try:
            candidates = await client.search_places(place["placeName"], region=args.region)
            resolved["places"][place["placeId"]] = {
                "current_name": place["placeName"],
                "candidates": candidates,
            }
        except MapProviderError as error:
            resolved["places"][place["placeId"]] = {
                "current_name": place["placeName"],
                "error": str(error),
                "candidates": [],
            }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"候选已写入 {args.output}；正式地点数据未被修改。")


if __name__ == "__main__":
    asyncio.run(main())
