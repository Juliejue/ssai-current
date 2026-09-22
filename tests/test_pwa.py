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
    assert '<script src="/place-photos.js"></script>' in html
    assert '<link rel="stylesheet" href="/current-moments.css">' in html
    assert _png_size(ROOT / "pwa/icon-180.png") == (180, 180)


def test_service_worker_caches_the_shell_but_never_intercepts_api_calls():
    worker = (ROOT / "sw.js").read_text(encoding="utf-8")

    for asset in ("/current/", "/current-client.js", "/mood-card.js", "/place-photos.js", "/current-moments.js",
                  "/current-moments.css", "/voice-worklet.mjs", "/manifest.webmanifest"):
        assert asset in worker
    assert "url.pathname.startsWith('/api/')" in worker


def test_iteration_ui_has_four_cities_media_and_no_removed_home_copy():
    html = (ROOT / "此在-current-原型.html").read_text(encoding="utf-8")
    moments = (ROOT / "current-moments.js").read_text(encoding="utf-8")
    for city in ("北京", "上海", "广州", "深圳"):
        assert city in moments
    assert 'id="moment-media"' in html
    assert "video/mp4" in html
    assert "想安静，想吃烤串" not in html
    assert "换成这个了。前一个我记下来" not in html
    assert 'id="social-name"' not in html
    assert 'id="match-chat"' not in html
    assert "演示私信 · 只在本次会话" not in html
    assert "不建主页、不显示昵称、不能私信" in html
    assert 'id="relay-join"' in html
    assert 'data-contribute="' in html
    assert "空间类型示意图" in html


def test_reviewed_place_photo_map_is_generated():
    photos = (ROOT / "place-photos.js").read_text(encoding="utf-8")
    assert "window.CURRENT_PLACE_PHOTOS" in photos
    assert photos.count("https://") >= 20
