"""Deterministic egress gate for model endpoints.

The model never chooses a URL. Deployment configuration is still validated so
a bad setting cannot send a user's words to localhost or an arbitrary host.
"""

from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlsplit


DEFAULT_MODEL_HOSTS = frozenset({
    "api.openai.com",
    "open.bigmodel.cn",
    "api.deepseek.com",
})


def checked_model_base_url(value: str | None) -> str | None:
    raw = (value or "https://api.openai.com/v1").strip().rstrip("/")
    try:
        parsed = urlsplit(raw)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        return None
    try:
        ipaddress.ip_address(host)
        return None  # Never allow an IP literal, even a public one.
    except ValueError:
        pass

    if (parsed.scheme != "https" or port not in (None, 443) or
            parsed.username or parsed.password or parsed.query or parsed.fragment or
            not host or host == "localhost" or host.endswith((".local", ".localhost", ".internal"))):
        return None

    # Extra providers are an explicit operator decision, never supplied by
    # a user message or model output. Exact hostnames only; no wildcards.
    configured = {
        item.strip().lower() for item in os.getenv("LLM_ALLOWED_HOSTS", "").split(",") if item.strip()
    }
    if host not in DEFAULT_MODEL_HOSTS | configured:
        return None
    return raw
