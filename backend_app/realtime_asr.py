"""Tencent Cloud realtime ASR URL signing.

The browser sends 16 kHz, 16-bit mono PCM directly to Tencent. The secret key
never leaves this API. URLs intentionally expire quickly.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
import uuid
from urllib.parse import quote


ASR_HOST = "asr.cloud.tencent.com"


def _sign(secret_key: str, raw: str) -> str:
    digest = hmac.new(secret_key.encode(), raw.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def build_asr_connect_url(voice_id: str | None = None) -> dict[str, str | int]:
    secret_id = os.getenv("TENCENT_SECRET_ID", "")
    secret_key = os.getenv("TENCENT_SECRET_KEY", "")
    app_id = os.getenv("ASR_APP_ID", "")
    if not (secret_id and secret_key and app_id):
        raise RuntimeError("ASR is not configured")

    timestamp = int(time.time())
    expired = timestamp + 120
    voice_id = voice_id or str(uuid.uuid4())
    params: dict[str, str | int] = {
        "secretid": secret_id,
        "engine_model_type": os.getenv("ASR_ENGINE_MODEL", "16k_zh"),
        "voice_id": voice_id,
        "timestamp": timestamp,
        "expired": expired,
        "nonce": timestamp,
        "voice_format": int(os.getenv("ASR_VOICE_FORMAT", "1")),
    }
    path = f"/asr/v2/{app_id}"
    query = "&".join(f"{key}={params[key]}" for key in sorted(params))
    raw = f"{ASR_HOST}{path}?{query}"
    signature = quote(_sign(secret_key, raw), safe="")
    return {
        "url": f"wss://{ASR_HOST}{path}?{query}&signature={signature}",
        "voice_id": voice_id,
        "expired": expired,
    }

