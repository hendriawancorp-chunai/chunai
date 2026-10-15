import pandas as pd
import pytest
from chunai import data as D


@pytest.fixture
def csv(tmp_path):
    p = tmp_path / "penjualan.csv"
    pd.DataFrame({"bulan": ["Jan", "Feb", "Mar", "Mar"], "omzet": [10, 12.5, None, None]}).to_csv(p, index=False)
    return p


def test_profile_reports_quality(csv):
    out = D.profile(D.load_table(csv))
    assert "Baris: 4" in out and "kosong=2" in out and "duplikat: 1" in out


def test_path_escape_blocked(tmp_path):
    with pytest.raises(ValueError):
        D.resolve_in(tmp_path, "../../etc/passwd")


def test_unsupported_format(tmp_path):
    (tmp_path / "a.exe").write_bytes(b"x")
    with pytest.raises(ValueError):
        D.load_table(tmp_path / "a.exe")


def test_chart_created_and_not_overwritten(csv, tmp_path):
    df = D.load_table(csv)
    a = D.make_chart(df, tmp_path / "g", "bar", "bulan", "omzet", "Omzet naik", "o")
    b = D.make_chart(df, tmp_path / "g", "bar", "bulan", "omzet", "Omzet naik", "o")
    assert a.exists() and b.exists() and a != b


def test_chart_bad_column(csv, tmp_path):
    with pytest.raises(ValueError):
        D.make_chart(D.load_table(csv), tmp_path, "line", "tidak_ada", "omzet", "x")


def test_long_title_is_wrapped(csv, tmp_path):
    long = "Omzet naik dari 120 juta di Januari ke puncak 210 juta di Desember dengan dua penurunan"
    path = D.make_chart(D.load_table(csv), tmp_path, "line", "bulan", "omzet", long, "t")
    assert path.exists()
