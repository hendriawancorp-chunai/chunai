"""Analisis data: profil tabel dan grafik sederhana. Semua path dikunci ke workspace."""
from __future__ import annotations

import itertools
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

# Palet aman buta warna (Okabe-Ito)
PALETTE = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#F0E442", "#000000"]
CHART_KINDS = {"bar", "line", "scatter", "hist"}


def resolve_in(workdir: Path, rel: str) -> Path:
    workdir = workdir.resolve()
    p = (workdir / rel).resolve()
    if p != workdir and workdir not in p.parents:
        raise ValueError("Path di luar workspace ditolak.")
    return p


def load_table(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"File tidak ditemukan: {path.name}")
    suffix = path.suffix.lower()
    if suffix in (".csv", ".tsv"):
        return pd.read_csv(path, sep=None, engine="python")
    if suffix in (".xlsx", ".xlsm"):
        return pd.read_excel(path)
    raise ValueError(f"Format tidak didukung: {suffix} (gunakan csv/tsv/xlsx)")


def profile(df: pd.DataFrame, max_cols: int = 40) -> str:
    lines = [f"Baris: {len(df)} | Kolom: {df.shape[1]}", "", "Kolom (tipe, kosong, unik):"]
    for c in itertools.islice(df.columns, max_cols):
        s = df[c]
        lines.append(f"- {c}: {s.dtype}, kosong={int(s.isna().sum())}, unik={int(s.nunique())}")
    num = df.select_dtypes("number")
    if not num.empty:
        lines += ["", "Ringkasan numerik:", num.describe().T.round(3).to_string()]
    lines += ["", "5 baris pertama:", df.head(5).to_string()]
    dup = int(df.duplicated().sum())
    lines += ["", f"Baris duplikat: {dup}"]
    return "\n".join(lines)


def make_chart(df: pd.DataFrame, out_dir: Path, kind: str, x: str | None, y: str | None,
               title: str, name: str = "grafik") -> Path:
    if kind not in CHART_KINDS:
        raise ValueError(f"kind harus salah satu dari {sorted(CHART_KINDS)}")
    for col in (x, y):
        if col is not None and col not in df.columns:
            raise ValueError(f"Kolom tidak ada: {col}")
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    color = PALETTE[0]
    if kind == "hist":
        ax.hist(df[x].dropna(), bins=20, color=color)
        ax.set_xlabel(x); ax.set_ylabel("Frekuensi")
    else:
        if x is None or y is None:
            raise ValueError("x dan y wajib untuk bar/line/scatter")
        if kind == "bar":
            ax.bar(df[x].astype(str), df[y], color=color)
            plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
        elif kind == "line":
            ax.plot(df[x], df[y], color=color, linewidth=2, marker="o", markersize=4)
        else:
            ax.scatter(df[x], df[y], color=color, alpha=0.8)
        ax.set_xlabel(x); ax.set_ylabel(y)
    ax.set_title(textwrap.fill(title, 62), loc="left", fontweight="bold", fontsize=11)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)[:40] or "grafik"
    path = out_dir / f"{safe}.png"
    for i in itertools.count(2):  # jangan menimpa file yang ada
        if not path.exists():
            break
        path = out_dir / f"{safe}_{i}.png"
    fig.savefig(path)
    plt.close(fig)
    return path
