"""Audit log append-only (JSONL): setiap aksi, keputusan, dan waktu tercatat."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .timeutil import now


class AuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: str, **data: Any) -> None:
        entry = {"ts": now().isoformat(timespec="seconds"), "event": event, **data}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]
