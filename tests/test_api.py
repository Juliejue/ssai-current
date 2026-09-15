from fastapi.testclient import TestClient

from backend_app.main import app


client = TestClient(app)


def test_health():
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_asr_capabilities_never_expose_credentials(monkeypatch):
    monkeypatch.setenv("TENCENT_SECRET_ID", "private-id")
    monkeypatch.setenv("TENCENT_SECRET_KEY", "private-key")
    monkeypatch.setenv("ASR_APP_ID", "private-app")

    response = client.get("/api/v1/asr/capabilities")

    assert response.status_code == 200
    assert response.json() == {"tencent_realtime": True}
    assert response.headers["cache-control"] == "no-store"
    assert "private" not in response.text


def test_urgent_request_does_not_return_places():
    response = client.post(
        "/api/v1/recommendations",
        json={"state": {"mood_id": "low", "risk_level": "urgent"}},
    )
    assert response.status_code == 200
    assert response.json()["blocked_by_safety"] is True
    assert response.json()["recommendations"] == []
