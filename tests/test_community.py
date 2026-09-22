from datetime import UTC, datetime

from fastapi.testclient import TestClient

from backend_app.community import _receipt_hash, expiry_for
from backend_app.main import app


client = TestClient(app)


def test_time_sensitive_contributions_expire_but_lasting_places_do_not():
    now = datetime(2026, 9, 23, 8, 0, tzinfo=UTC)
    assert (expiry_for("timed_beauty", now) - now).total_seconds() == 3600
    assert (expiry_for("sensory", now) - now).total_seconds() == 10800
    assert (expiry_for("seasonal", now) - now).days == 7
    assert expiry_for("lasting_place", now) is None


def test_receipt_is_stored_as_one_way_hash():
    token = "private-delete-receipt"
    digest = _receipt_hash(token)
    assert token not in digest
    assert len(digest) == 64


def test_submission_without_database_stays_an_unpublished_local_draft(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    response = client.post(
        "/api/v1/community/contributions",
        json={
            "place_name": "一棵树下",
            "city": "上海",
            "reason": "傍晚有一小片安静的光",
            "kind": "timed_beauty",
            "mood_id": "quiet",
            "media_count": 1,
        },
    )
    assert response.status_code == 202
    assert response.json() == {
        "accepted": True,
        "persisted": False,
        "contribution_id": None,
        "receipt_token": None,
        "moderation_status": "pending",
    }


def test_approved_feed_is_empty_without_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    response = client.get("/api/v1/community/contributions?city=上海")
    assert response.status_code == 200
    assert response.json() == {"contributions": []}
