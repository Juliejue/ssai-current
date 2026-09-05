from backend_app.recommender import load_catalog, recommend
from backend_app.schemas import NeedState, RecommendRequest


def test_catalog_contains_all_prototype_places():
    assert len(load_catalog()["PLACES"]) == 26


def test_free_request_only_returns_free_places():
    request = RecommendRequest(state=NeedState(mood_id="low", need_keys=["free"], budget_level="free"))
    results = recommend(request)
    catalog = {place["placeId"]: place for place in load_catalog()["PLACES"]}
    assert results
    assert all(catalog[item.place_id]["free"] for item in results)


def test_rejected_place_is_not_returned():
    baseline = recommend(RecommendRequest(state=NeedState(mood_id="quiet")))
    rejected = baseline[0].place_id
    after = recommend(RecommendRequest(state=NeedState(mood_id="quiet"), rejected_place_ids=[rejected]))
    assert rejected not in {item.place_id for item in after}

