"""Pembatas pekerjaan berat (Chromium, LibreOffice, ffmpeg): secara default hanya satu berjalan sekaligus.
Menjaga RAM di komputer/VPS kecil dan menjalankan pekerjaan blocking di thread agar bot tetap responsif."""
from __future__ import annotations

import asyncio
import os
import weakref
from contextlib import asynccontextmanager

_sems: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = weakref.WeakKeyDictionary()


def slots() -> int:
    try:
        return max(1, int(os.environ.get("CHUNAI_HEAVY_SLOTS", "1")))
    except ValueError:
        return 1


@asynccontextmanager
async def heavy():
    loop = asyncio.get_running_loop()
    sem = _sems.get(loop)
    if sem is None:
        sem = _sems[loop] = asyncio.Semaphore(slots())
    async with sem:
        yield


async def run_heavy(func, *args, **kwargs):
    """Jalankan fungsi blocking di thread, dengan slot pekerjaan berat."""
    async with heavy():
        return await asyncio.to_thread(func, *args, **kwargs)
