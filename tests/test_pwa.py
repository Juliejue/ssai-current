from __future__ import annotations

import json
import pathlib
import struct


ROOT = pathlib.Path(__file__).parents[1]


def _png_size(path: pathlib.Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_manifest_has_a_standalone_mobile_shell_and_real_icons():
    manifest = json.loads((ROOT / "manifest.webmanifest").read_text(encoding="utf-8"))

    assert manifest["display"] == "standalone"
    assert manifest["start_url"].startswith("/current/")
    assert manifest["theme_color"] == "#F0F3F2"
    sizes = {icon["sizes"]: ROOT / icon["src"].lstrip("/") for icon in manifest["icons"]}
    assert _png_size(sizes["192x192"]) == (192, 192)
    assert _png_size(sizes["512x512"]) == (512, 512)


def test_html_links_the_manifest_and_ios_icon():
    html = (ROOT / "此在-current-原型.html").read_text(encoding="utf-8")

    assert 'rel="manifest" href="/manifest.webmanifest"' in html
    assert 'name="apple-mobile-web-app-capable" content="yes"' in html
    assert 'rel="apple-touch-icon" href="/pwa/icon-180.png"' in html
    assert '<script src="/mood-card.js"></script>' in html
    assert '<script src="/current-moments.js"></script>' in html
    assert '<link rel="stylesheet" href="/current-moments.css">' in html
    assert _png_size(ROOT / "pwa/icon-180.png") == (180, 180)


def test_service_worker_caches_the_shell_but_never_intercepts_api_calls():
    worker = (ROOT / "sw.js").read_text(encoding="utf-8")

    for asset in ("/current/", "/current-client.js", "/mood-card.js", "/current-moments.js",
                  "/current-moments.css", "/voice-worklet.mjs", "/manifest.webmanifest"):
        assert asset in worker
    assert "url.pathname.startsWith('/api/')" in worker
