import json
from pathlib import Path

from backend_app.discovery import to_place
from backend_app.place_photos import reviewed_photos

ROOT = Path(__file__).parents[1]


def poi(name, **changes):
    return {"name": name, "id": "river-test", "latitude": 22.395, "longitude": 113.976,
            "cityname": "香港", "photos": [], "distance": 200, **changes}


def test_hong_kong_river_uses_reviewed_local_photos_in_both_scripts():
    for name in ("屯门河道", "屯門河道", "屯门河", "Tuen Mun River Channel"):
        place = to_place(poi(name), "river")
        assert place["photos"][0] == "/assets/places/hk/tuen-mun-river-1.webp"
        assert len(place["photos"]) == 3
        assert place["photo_attributions"][0]["source_url"].startswith("https://commons.wikimedia.org/wiki/File:")
        assert place["amap"]["provider_place_id"] == "river-test"


def test_curated_photos_do_not_replace_an_unrelated_place_or_other_city():
    assert reviewed_photos(poi("香港公园酒店")) == []
    assert reviewed_photos(poi("屯门河道", latitude=39.9, longitude=116.4)) == []
    assert reviewed_photos(poi("香港公园", cityname="深圳市")) == []
    assert reviewed_photos({"name": "维多利亚公园", "cityname": "上海"}) == []
    assert reviewed_photos(poi("未知公园")) == []
    original = to_place(poi("未知公园", photos=[{"url":"http://example.com/park.jpg"}]), "park")
    assert original["photos"] == ["https://example.com/park.jpg"]


def test_park_entrance_alias_matches_without_matching_a_shop():
    assert reviewed_photos(poi("屯門公園（北門）"))
    assert not reviewed_photos(poi("屯門公園咖啡店"))


def test_all_catalog_photos_are_local_real_assets_with_complete_attribution():
    records = json.loads((ROOT / "backend_app/data/hong_kong_photos.json").read_text())["places"]
    assert len(records) >= 40
    for place in records:
        assert place["photos"]
        for photo in place["photos"]:
            assert (ROOT / photo["url"].lstrip("/")).stat().st_size > 1000
            assert photo["author"] and photo["license"].startswith("CC BY")
            assert photo["source_url"].startswith("https://commons.wikimedia.org/wiki/File:")
            assert photo["license_url"].startswith("https://creativecommons.org/")
