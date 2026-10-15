"""Tool MCP untuk media (gambar & video)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from claude_agent_sdk import tool

from . import media as M


def media_tools(workdir: Path):
    workdir = workdir.resolve()
    out = workdir / "output"

    def ok(t): return {"content": [{"type": "text", "text": t}]}
    def err(t): return {"content": [{"type": "text", "text": t}], "is_error": True}
    rel = lambda p: str(Path(p).relative_to(workdir))

    @tool("buat_gambar",
          "Buat gambar PNG (poster, infografis, kartu media sosial, banner, diagram) dari HTML+CSS inline. "
          "Tanpa JavaScript dan tanpa internet: pakai data: URI atau gambar di workspace (path relatif dari workspace). "
          "Ukuran default 1080x1080; untuk 16:9 pakai 1280x720. Hasil di output/. Periksa hasilnya dengan Read.",
          {"html": str, "name": str, "width": int, "height": int})
    async def buat_gambar(args):
        try:
            path = M.unique(out / f"{M.safe_name(args.get('name'), 'gambar')}.png")
            blocked = await M.render_html(args["html"], path, workdir, int(args.get("width") or 1080), int(args.get("height") or 1080))
            msg = f"Gambar tersimpan: {rel(path)}"
            if blocked:
                msg += "\nPermintaan eksternal DIBLOKIR (tidak dimuat): " + ", ".join(blocked[:5])
            return ok(msg)
        except Exception as e:
            return err(f"Gagal membuat gambar: {type(e).__name__}: {e}")

    @tool("edit_gambar",
          "Edit gambar di workspace. operasi: list objek {op: resize|crop|rotate|grayscale|text, ...}. "
          "resize {width,height,fit:contain|cover}; crop {left,top,right,bottom}; rotate {degrees}; text {text,x,y,size,color}. "
          "Hasil disimpan sebagai file baru di output/ (asli tidak diubah).",
          {"path": str, "operasi": list, "name": str, "format": str})
    async def edit_gambar(args):
        try:
            src = M.inside(workdir, args["path"])
            ext = "jpg" if str(args.get("format", "")).lower() in ("jpg", "jpeg") else "png"
            path = M.unique(out / f"{M.safe_name(args.get('name'), src.stem + '_edit')}.{ext}")
            M.edit_image(src, path, list(args["operasi"]))
            return ok(f"Gambar tersimpan: {rel(path)}")
        except Exception as e:
            return err(f"Gagal mengedit gambar: {type(e).__name__}: {e}")

    @tool("buat_video",
          "Buat video MP4 dari adegan: scenes = list {image: path PNG di workspace | html: str, durasi: detik (1-30)}. "
          "Transisi fade otomatis, total maks 300 dtk. Opsional audio: path musik/narasi di workspace. Hasil di output/.",
          {"scenes": list, "name": str, "width": int, "height": int, "fps": int, "audio": str})
    async def buat_video(args):
        try:
            w, h = int(args.get("width") or 1280), int(args.get("height") or 720)
            frames, durs = [], []
            tmp = workdir / ".tmp" / "frames"
            tmp.mkdir(parents=True, exist_ok=True)
            for i, sc in enumerate(args["scenes"]):
                if sc.get("html"):
                    fp = tmp / f"f{i}.png"
                    await M.render_html(sc["html"], fp, workdir, w, h)
                elif sc.get("image"):
                    fp = M.inside(workdir, sc["image"])
                else:
                    raise ValueError(f"Adegan {i + 1}: butuh 'image' atau 'html'.")
                frames.append(fp); durs.append(float(sc.get("durasi", 4)))
            path = M.unique(out / f"{M.safe_name(args.get('name'), 'video')}.mp4")
            audio = M.inside(workdir, args["audio"]) if args.get("audio") else None
            await asyncio.to_thread(M.make_video, frames, durs, path, (w, h), int(args.get("fps") or 24), 0.6, audio)
            info = M.probe(path)
            return ok(f"Video tersimpan: {rel(path)} ({info.get('width')}x{info.get('height')}, {float(info.get('duration', 0)):.1f} dtk)")
        except Exception as e:
            return err(f"Gagal membuat video: {type(e).__name__}: {e}")

    @tool("slide_ke_video", "Ubah PPTX di workspace menjadi video MP4: tiap slide = satu adegan dengan durasi tetap.",
          {"path": str, "detik_per_slide": int, "name": str})
    async def slide_ke_video(args):
        try:
            src = M.inside(workdir, args["path"])
            d = float(args.get("detik_per_slide") or 6)
            frames = await asyncio.to_thread(M.deck_to_frames, src, workdir / ".tmp" / "deck")
            path = M.unique(out / f"{M.safe_name(args.get('name'), src.stem + '_video')}.mp4")
            await asyncio.to_thread(M.make_video, frames, [d] * len(frames), path, (1280, 720), 24)
            info = M.probe(path)
            return ok(f"Video tersimpan: {rel(path)} ({len(frames)} slide, {float(info.get('duration', 0)):.1f} dtk)")
        except Exception as e:
            return err(f"Gagal membuat video: {type(e).__name__}: {e}")

    return [buat_gambar, edit_gambar, buat_video, slide_ke_video]
