import json
from pathlib import Path

import pytest
from PIL import Image

from chunai import media as M
from chunai.browser import find_chromium

pytestmark = pytest.mark.skipif(not find_chromium(), reason="Chromium tidak tersedia")


async def test_html_to_png_size_and_blocks_external(tmp_path):
    out = tmp_path / "o.png"
    blocked = await M.render_html("<div style='background:#0070c0;width:100%;height:100%'>"
                                  "<img src='http://evil.example/x.png'><script>fetch('http://evil.example')</script></div>",
                                  out, tmp_path, 640, 360)
    assert Image.open(out).size == (640, 360)
    assert any("evil.example" in b for b in blocked)


async def test_local_image_allowed_but_outside_workspace_blocked(tmp_path):
    ws = tmp_path / "ws"; ws.mkdir()
    Image.new("RGB", (50, 50), "red").save(ws / "a.png")
    Image.new("RGB", (50, 50), "blue").save(tmp_path / "luar.png")
    blocked = await M.render_html(f"<img src='a.png'><img src='{(tmp_path / 'luar.png').as_uri()}'>", ws / "o.png", ws, 200, 200)
    assert len(blocked) == 1 and "luar.png" in blocked[0]


async def test_size_limits(tmp_path):
    with pytest.raises(ValueError):
        await M.render_html("x", tmp_path / "o.png", tmp_path, 9000, 9000)


def test_edit_image_ops(tmp_path):
    src = tmp_path / "s.png"; Image.new("RGB", (400, 200), "green").save(src)
    out = M.edit_image(src, tmp_path / "e.jpg", [{"op": "resize", "width": 100, "height": 100, "fit": "cover"},
                                                  {"op": "grayscale"}, {"op": "text", "text": "Hai", "x": 5, "y": 5}])
    assert Image.open(out).size == (100, 100)
    with pytest.raises(ValueError):
        M.edit_image(src, tmp_path / "x.png", [{"op": "hack"}])


def test_path_escape_blocked(tmp_path):
    with pytest.raises(ValueError):
        M.inside(tmp_path, "../../etc/passwd")


@pytest.mark.skipif(not M.ffmpeg_available(), reason="ffmpeg tidak tersedia")
def test_video_from_frames(tmp_path):
    fr = []
    for i, c in enumerate(("red", "green", "blue")):
        p = tmp_path / f"{i}.png"; Image.new("RGB", (640, 360), c).save(p); fr.append(p)
    out = M.make_video(fr, [2, 2, 2], tmp_path / "v.mp4", (640, 360), 12)
    info = M.probe(out)
    assert info["width"] == "640" and info["codec_name"] == "h264"
    assert 6.0 <= float(info["duration"]) < 7.0          # jumlah adegan + 1 transisi


def test_video_validation(tmp_path):
    p = tmp_path / "a.png"; Image.new("RGB", (10, 10)).save(p)
    with pytest.raises(ValueError):
        M.make_video([p], [100], tmp_path / "v.mp4")
    with pytest.raises(ValueError):
        M.make_video([p, p], [3], tmp_path / "v.mp4")
