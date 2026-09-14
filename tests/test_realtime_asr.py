from __future__ import annotations

import base64
import hashlib
import hmac
from urllib.parse import parse_qs, urlsplit

import pytest

from backend_app import realtime_asr


def test_signature_matches_tencent_websocket_contract(monkeypatch):
    monkeypatch.setenv("TENCENT_SECRET_ID", "test-secret-id")
    monkeypatch.setenv("TENCENT_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("ASR_APP_ID", "1234567890")
    monkeypatch.setattr(realtime_asr.time, "time", lambda: 1_700_000_000)

    result = realtime_asr.build_asr_connect_url("voice-test-id")
    parsed = urlsplit(result["url"])
    params = {key: values[0] for key, values in parse_qs(parsed.query).items()}

    assert parsed.scheme == "wss"
    assert parsed.netloc == "asr.cloud.tencent.com"
    assert parsed.path == "/asr/v2/1234567890"
    assert params["engine_model_type"] == "16k_zh"
    assert params["voice_format"] == "1"
    assert params["voice_id"] == "voice-test-id"
    assert params["timestamp"] == "1700000000"
    assert params["expired"] == "1700000120"
    assert len(params["nonce"]) <= 10

    unsigned = {key: value for key, value in params.items() if key != "signature"}
    query = "&".join(f"{key}={unsigned[key]}" for key in sorted(unsigned))
    raw = f"asr.cloud.tencent.com/asr/v2/1234567890?{query}"
    expected = base64.b64encode(
        hmac.new(b"test-secret-key", raw.encode(), hashlib.sha1).digest()
    ).decode()
    assert params["signature"] == expected


def test_signature_requires_server_credentials(monkeypatch):
    for key in ("TENCENT_SECRET_ID", "TENCENT_SECRET_KEY", "ASR_APP_ID"):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(RuntimeError, match="ASR is not configured"):
        realtime_asr.build_asr_connect_url("voice-test-id")
