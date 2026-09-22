from fastapi.testclient import TestClient

from backend_app.main import app
from backend_app.relay import safe_payload


client = TestClient(app)


def test_relay_session_carries_structured_events_without_private_fields(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    session = client.post("/api/v1/relay/sessions")
    assert session.status_code == 200
    code = session.json()["code"]
    assert len(code) == 6
    assert session.json()["durable"] is False

    sent = client.post(
        f"/api/v1/relay/{code}/events",
        json={
            "event_type": "feedback",
            "payload": {
                "place_id": "liangmahe",
                "place_name": "亮马河",
                "change_score": 2,
                "factors": ["有风", "能一直走"],
                "note": "这句私密原话不能跨设备",
                "latitude": 39.9,
            },
        },
    )
    assert sent.status_code == 202

    read = client.get(f"/api/v1/relay/{code}?after=0")
    assert read.status_code == 200
    event = read.json()["events"][0]
    assert event["event_type"] == "feedback"
    assert event["payload"] == {
        "place_id": "liangmahe",
        "place_name": "亮马河",
        "change_score": 2,
        "factors": ["有风", "能一直走"],
    }


def test_relay_after_cursor_and_unknown_session(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    code = client.post("/api/v1/relay/sessions").json()["code"]
    first = client.post(
        f"/api/v1/relay/{code}/events",
        json={"event_type": "arrived", "payload": {"place_id": "x", "place_name": "一处"}},
    ).json()["sequence"]
    assert client.get(f"/api/v1/relay/{code}?after={first}").json()["events"] == []
    assert client.get("/api/v1/relay/AAAAAA").status_code == 404


def test_relay_payload_clamps_and_limits_values():
    output = safe_payload(
        "feedback",
        {"change_score": 99, "factors": ["x" * 80] * 10, "unknown": "drop"},
    )
    assert output["change_score"] == 3
    assert len(output["factors"]) == 6
    assert len(output["factors"][0]) == 40
    assert "unknown" not in output
