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


def test_iteration_ui_has_nationwide_moments_media_and_no_removed_home_copy():
    html = (ROOT / "此在-current-原型.html").read_text(encoding="utf-8")
    moments = (ROOT / "current-moments.js").read_text(encoding="utf-8")
    for city in ("北京", "上海", "广州", "深圳", "香港", "成都", "杭州", "南京"):
        assert city in moments
    for control in ("moment-media-library", "moment-media-camera", "moment-media-files"):
        assert f'id="{control}"' in html
    for label in ("相册", "拍摄", "选取文件"):
        assert label in html
    files_input = html[html.index('id="moment-media-files"'):][:180]
    assert "accept=" not in files_input
    assert "getUserMedia({video:" in html
    assert "window.showOpenFilePicker" in html
    assert "next.place_types = []" in html
    assert 'file.type.startsWith("video/")' in html
    assert "想安静，想吃烤串" not in html
    assert "换成这个了。前一个我记下来" not in html
    assert 'id="social-name"' not in html
    assert 'id="match-chat"' not in html
    assert "演示私信 · 只在本次会话" not in html
    assert 'id="relay-join"' in html
    assert 'data-contribute="' in html
    assert "空间类型示意图" in html


def test_screenshot_regressions_keep_copy_and_controls_clean():
    html = (ROOT / "此在-current-原型.html").read_text(encoding="utf-8")
    settings = html[html.index("function renderSettings("):html.index("function reachBlockedText(")]
    moments = html[html.index("function momentCard("):html.index("function renderMoments(")]
    nearby = html[html.index("function renderNearby("):html.index("function miniOf(")]

    for removed in ("只打开你愿意给的", "存：结构化之后的需求", "不存：原话、语音", "向我推荐可能认识的人", "私信权限"):
        assert removed not in settings
    for removed in ("本机数据", "我们的边界", "清空这台设备上的全部记录"):
        assert removed not in settings
    assert 'id="font-scale"' in settings
    assert 'id="preference-mic"' in settings
    for removed in ("还剩约", "演示种子", "Unsplash License"):
        assert removed not in moments
    for removed in ("这里对去过的人有没有帮助", "只显示汇总", "现在攒到哪一步", "匿名汇总是怎么算的"):
        assert removed not in nearby
    assert "还没有足够的匿名到访记录" in nearby


def test_reviewed_place_photo_map_is_generated():
    photos = (ROOT / "place-photos.js").read_text(encoding="utf-8")
    assert "window.CURRENT_PLACE_PHOTOS" in photos
    assert photos.count("https://") >= 20
