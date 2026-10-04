"""Reviewed photographs supplement sparse Hong Kong map-provider imagery.

Only an exact place alias within Hong Kong can match. Image curation does not
change a place's navigation, opening hours, recommendation score or visit status.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


def normalize_name(name: str) -> str:
    name = re.sub(r"[（(](?:东|東|西|南|北)?(?:门|門|入口|出入口)[）)]$", "", name.strip())
    return re.sub(r"[\s·•,，()（）_-]", "", name).casefold()


@lru_cache(maxsize=1)
def catalog() -> dict[str, dict[str, Any]]:
    path = Path(__file__).parent / "data" / "hong_kong_photos.json"
    records = json.loads(path.read_text(encoding="utf-8"))["places"]
    return {normalize_name(alias): record for record in records for alias in record["aliases"]}


def reviewed_photos(poi: dict[str, Any]) -> list[dict[str, str]]:
    city = str(poi.get("cityname") or "").casefold()
    hong_kong_names = {"香港", "香港特别行政区", "香港特別行政區", "hong kong", "hong kong sar"}
    if city and city not in hong_kong_names:
        return []
    latitude, longitude = poi.get("latitude"), poi.get("longitude")
    if latitude is not None and longitude is not None:
        try:
            # Hong Kong's boundary, rather than an ambiguous substring of a name.
            in_hong_kong = 22.14 <= float(latitude) <= 22.57 and 113.82 <= float(longitude) <= 114.46
        except (TypeError, ValueError):
            return []
    else:
        in_hong_kong = city in hong_kong_names
    if not in_hong_kong:
        return []
    record = catalog().get(normalize_name(str(poi.get("name") or "")))
    return [dict(photo) for photo in record["photos"]] if record else []
