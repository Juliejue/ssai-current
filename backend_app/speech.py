"""Fixed Xiaozai neural voice; credentials and text remain server-side/transient."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime, timezone

import httpx

HOST = "tts.tencentcloudapi.com"
VOICE_ID = 502001  # 智小柔：超自然聊天女声，不使用设备系统朗读。


def configured() -> bool:
    return bool(os.getenv("TENCENT_SECRET_ID") and os.getenv("TENCENT_SECRET_KEY"))


def signed_headers(body: str, timestamp: int) -> dict[str, str]:
    date = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d")
    canonical_headers = f"content-type:application/json; charset=utf-8\nhost:{HOST}\n"
    canonical = "POST\n/\n\n" + canonical_headers + "\ncontent-type;host\n" + hashlib.sha256(body.encode()).hexdigest()
    scope = f"{date}/tts/tc3_request"
    to_sign = f"TC3-HMAC-SHA256\n{timestamp}\n{scope}\n" + hashlib.sha256(canonical.encode()).hexdigest()
    def sign(key: bytes, value: str) -> bytes:
        return hmac.new(key, value.encode(), hashlib.sha256).digest()
    key = sign(("TC3" + os.environ["TENCENT_SECRET_KEY"]).encode(), date)
    key = sign(sign(key, "tts"), "tc3_request")
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json; charset=utf-8", "Host": HOST,
        "Authorization": f"TC3-HMAC-SHA256 Credential={os.environ['TENCENT_SECRET_ID']}/{scope}, SignedHeaders=content-type;host, Signature={signature}",
        "X-TC-Action": "TextToVoice", "X-TC-Version": "2019-08-23", "X-TC-Timestamp": str(timestamp),
    }


async def synthesize(text: str, lang: str = "zh") -> bytes:
    if not configured():
        raise RuntimeError("小在的自然声音尚未配置，请先使用文字。")
    body = json.dumps({
        "Text": text.strip(), "SessionId": str(uuid.uuid4()), "ModelType": 1,
        "VoiceType": VOICE_ID, "Speed": -0.35, "Volume": 0,
        "SampleRate": 24000, "Codec": "mp3", "PrimaryLanguage": 2 if lang == "en" else 1,
    }, ensure_ascii=False, separators=(",", ":"))
    try:
        async with httpx.AsyncClient(timeout=18) as client:
            response = await client.post(f"https://{HOST}", content=body.encode(), headers=signed_headers(body, int(time.time())))
            response.raise_for_status()
            result = response.json()["Response"]
        if "Error" in result:
            code = result["Error"].get("Code", "")
            if "AuthFailure" in code or "UnauthorizedOperation" in code:
                raise RuntimeError("自然声音暂无使用权限，请在腾讯云开通 TTS 并授权语音合成。")
            if "AppIdNotRegistered" in code or "Resource" in code or "FailedOperation" in code:
                raise RuntimeError("自然声音暂不可用，请检查腾讯云 TTS 开通状态与音色额度。")
            raise RuntimeError("自然声音生成失败，请稍后重试。")
        audio = base64.b64decode(result["Audio"], validate=True)
        if not audio or len(audio) > 5_000_000:
            raise ValueError("invalid audio")
        return audio
    except (httpx.HTTPError, ValueError, KeyError) as error:
        raise RuntimeError("自然声音暂时连接不上，请先使用文字。") from error
