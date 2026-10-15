"""Media: desain grafis dari HTML/CSS -> PNG, edit gambar, video dari adegan/slide (ffmpeg).
Render HTML tanpa JavaScript dan tanpa akses jaringan (permintaan eksternal diblokir)."""
from __future__ import annotations

import itertools
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .browser import find_chromium
from .office.render import to_pdf, to_pngs

MAX_PIXELS = 4096 * 4096
FONT_CANDIDATES = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/opentype/inter/Inter-Bold.otf"]


def unique(path: Path) -> Path:
    if not path.exists():
        return path
    for i in itertools.count(2):
        p = path.with_name(f"{path.stem}_{i}{path.suffix}")
        if not p.exists():
            return p


def safe_name(n: str, default: str) -> str:
    return re.sub(r"[^\w-]", "_", n or default)[:50] or default


def inside(workdir: Path, rel: str) -> Path:
    workdir = workdir.resolve()
    p = (workdir / rel).resolve()
    if p != workdir and workdir not in p.parents:
        raise ValueError("Path di luar workspace ditolak.")
    return p


# ---------------- HTML -> PNG ----------------
async def render_html(html: str, out: Path, workdir: Path, width: int = 1080, height: int = 1080) -> list[str]:
    """Kembalikan daftar URL yang diblokir. Gambar lokal boleh dirujuk relatif terhadap workspace."""
    if width * height > MAX_PIXELS or width < 100 or height < 100:
        raise ValueError("Ukuran tidak valid (100px .. 4096x4096).")
    from playwright.async_api import async_playwright
    workdir = workdir.resolve()
    tmp = workdir / ".tmp"
    tmp.mkdir(exist_ok=True)
    page_file = tmp / "render.html"
    page_file.write_text(html if "<html" in html.lower() else f"<!doctype html><html><head><meta charset='utf-8'></head><body style='margin:0'>{html}</body></html>",
                         encoding="utf-8")
    blocked: list[str] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=find_chromium(), args=["--no-sandbox"])
        ctx = await browser.new_context(viewport={"width": width, "height": height}, java_script_enabled=False, device_scale_factor=1)

        async def guard(route):
            url = route.request.url
            if url.startswith("data:") or (url.startswith("file://") and Path(url[7:].split("?")[0]).resolve().is_relative_to(workdir)):
                await route.continue_()
            else:
                blocked.append(url[:120])
                await route.abort()

        await ctx.route("**/*", guard)
        page = await ctx.new_page()
        await page.goto(page_file.as_uri())
        await page.wait_for_timeout(150)
        out.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": width, "height": height})
        await browser.close()
    page_file.unlink(missing_ok=True)
    return blocked


# ---------------- edit gambar ----------------
def edit_image(src: Path, out: Path, ops: list[dict]) -> Path:
    img = Image.open(src)
    img = ImageOps.exif_transpose(img).convert("RGBA")
    for op in ops:
        k = op.get("op")
        if k == "resize":
            w, h = int(op.get("width", 0)), int(op.get("height", 0))
            if w * h > MAX_PIXELS and w and h:
                raise ValueError("Ukuran terlalu besar.")
            if w and h and op.get("fit", "contain") == "cover":
                img = ImageOps.fit(img, (w, h))
            elif w and h:
                img = ImageOps.contain(img, (w, h))
            elif w:
                img = img.resize((w, int(img.height * w / img.width)))
            elif h:
                img = img.resize((int(img.width * h / img.height), h))
        elif k == "crop":
            img = img.crop((int(op["left"]), int(op["top"]), int(op["right"]), int(op["bottom"])))
        elif k == "rotate":
            img = img.rotate(-float(op["degrees"]), expand=True)
        elif k == "grayscale":
            img = ImageOps.grayscale(img).convert("RGBA")
        elif k == "text":
            d = ImageDraw.Draw(img)
            font = next((ImageFont.truetype(f, int(op.get("size", 40))) for f in FONT_CANDIDATES if Path(f).exists()), ImageFont.load_default())
            d.text((int(op.get("x", 20)), int(op.get("y", 20))), str(op["text"]), fill=op.get("color", "#FFFFFF"), font=font,
                   stroke_width=int(op.get("stroke", 2)), stroke_fill=op.get("stroke_color", "#000000"))
        else:
            raise ValueError(f"Operasi tidak dikenal: {k} (resize|crop|rotate|grayscale|text)")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() in (".jpg", ".jpeg"):
        img = img.convert("RGB")
    img.save(out)
    return out


# ---------------- video ----------------
def ffmpeg_available() -> bool:
    return bool(shutil.which("ffmpeg"))


def make_video(frames: list[Path], durations: list[float], out: Path, size=(1280, 720), fps: int = 24,
               transition: float = 0.6, audio: Path | None = None) -> Path:
    if not ffmpeg_available():
        raise RuntimeError("ffmpeg tidak tersedia.")
    if not frames or len(frames) != len(durations):
        raise ValueError("Jumlah gambar dan durasi harus sama dan tidak kosong.")
    if any(d < 1 or d > 30 for d in durations) or sum(durations) > 300:
        raise ValueError("Durasi adegan 1-30 dtk dan total maksimal 300 dtk.")
    w, h = size
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    t = min(transition, min(durations) / 2) if len(frames) > 1 else 0
    for f, d in zip(frames, durations):
        cmd += ["-loop", "1", "-t", f"{d + t:.2f}", "-i", str(f)]
    parts = [f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=white,setsar=1,fps={fps},format=yuv420p[v{i}]"
             for i in range(len(frames))]
    last, acc = "v0", durations[0]
    for i in range(1, len(frames)):
        parts.append(f"[{last}][v{i}]xfade=transition=fade:duration={t:.2f}:offset={acc:.2f}[x{i}]")
        last, acc = f"x{i}", acc + durations[i]
    cmd += ["-filter_complex", ";".join(parts), "-map", f"[{last}]"]
    if audio:
        cmd += ["-i", str(audio), "-map", f"{len(frames)}:a", "-shortest", "-c:a", "aac"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-movflags", "+faststart", str(out)]
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg gagal: {r.stderr[-300:]}")
    return out


def deck_to_frames(pptx: Path, out_dir: Path, dpi: int = 110) -> list[Path]:
    pdf = to_pdf(pptx, out_dir)
    return to_pngs(pdf, out_dir, dpi=dpi)


def probe(path: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height,codec_name:format=duration",
                        "-of", "default=nw=1", str(path)], capture_output=True, text=True)
    return dict(l.split("=", 1) for l in r.stdout.splitlines() if "=" in l)
