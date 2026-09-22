from backend_app.space_profiles import MIN_VERIFIED_SAMPLES, aggregate_verified_visits, apply_profile
from backend_app.recommender import _rank, _to_recommendation, load_catalog
from backend_app.schemas import NeedState, RecommendRequest


def test_profile_stays_out_of_ranking_until_five_verified_visits():
    profile = aggregate_verified_visits([(2, ["quiet"])] * (MIN_VERIFIED_SAMPLES - 1))
    assert profile["sample_size"] == 4
    assert profile["tags"] == {}
    place = {"tags": {"q": 0.5}}
    assert apply_profile(place, profile) is place


def test_verified_factors_conservatively_refine_existing_tags():
    rows = [
        (2, ["quiet", "fewpeople", "seat"]),
        (1, ["quiet", "fewpeople"]),
        (3, ["quiet", "seat"]),
        (2, ["quiet", "fewpeople"]),
        (1, ["quiet"]),
    ]
    profile = aggregate_verified_visits(rows)
    assert profile["tags"]["q"] == 1.0
    assert profile["confidence"]["q"] == 1.0
    place = {"placeId": "p", "tags": {"q": 0.6, "c": 0.7, "st": 0.4}}
    adjusted = apply_profile(place, profile)
    assert 0.6 < adjusted["tags"]["q"] < 1.0
    assert adjusted["tags"]["c"] < 0.7
    assert adjusted["profile_sample_size"] == 5
    assert place["tags"]["q"] == 0.6, "cached editorial data must not be mutated"


def test_verified_profile_is_visible_in_recommendation_evidence():
    place_id = load_catalog()["PLACES"][0]["placeId"]
    profile = {
        "tags": {"q": 1.0},
        "confidence": {"q": 1.0},
        "sample_size": 7,
    }
    request = RecommendRequest(state=NeedState(mood_id="quiet"), limit=10)
    ranked = _rank(request, profile_overlays={place_id: profile})
    score, place, breakdown = next(item for item in ranked if item[1]["placeId"] == place_id)
    recommendation = _to_recommendation(score, place, breakdown, request.state)

    assert recommendation.sample_size == 7
    assert recommendation.low_support is False
    assert recommendation.attribute_source == "verified_feedback"
