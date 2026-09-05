from fastapi.testclient import TestClient

from backend_app.main import app


client = TestClient(app)


def test_health():
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_urgent_request_does_not_return_places():
    response = client.post(
        "/api/v1/recommendations",
        json={"state": {"mood_id": "low", "risk_level": "urgent"}},
    )
    assert response.status_code == 200
    assert response.json()["blocked_by_safety"] is True
    assert response.json()["recommendations"] == []

