import os
import stat
import sys
import textwrap

from chunai.auth import extract_token, run_setup_token
from chunai.envfile import save_env_var

TOKEN = "sk-ant-oat01-" + "Ab3_-" * 20          # 113 karakter


def test_extract_simple():
    assert extract_token(f"Your token:\n{TOKEN}\nStore it securely.") == TOKEN


def test_extract_strips_ansi_and_cr():
    raw = f"\x1b[1mToken\x1b[0m: \x1b[32m{TOKEN}\x1b[0m\r\n\x1b]0;judul\x07selesai\r\n"
    assert extract_token(raw) == TOKEN


def test_extract_joins_token_wrapped_exactly_at_terminal_width():
    a, b, c = TOKEN[:78], TOKEN[78:], ""                        # 2 spasi + 78 = 80 kolom penuh
    assert extract_token(f"Token (1 tahun):\n  {a}\n  {b}\n\nSimpan baik-baik.") == TOKEN


def test_extract_does_not_join_short_word_after_unwrapped_token():
    assert extract_token(f"Token: {TOKEN}\nselesai\n") == TOKEN


def test_extract_does_not_swallow_following_prose():
    assert extract_token(f"{TOKEN}\nStore this token securely. You won't see it again.") == TOKEN


def test_extract_none_when_absent_or_too_short():
    assert extract_token("Login berhasil tanpa token") is None
    assert extract_token("sk-ant-oat01-abc") is None


def test_save_env_var_updates_in_place_and_keeps_others(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# komentar\nA=1\nCLAUDE_CODE_OAUTH_TOKEN=\nB=dua\n")
    save_env_var("CLAUDE_CODE_OAUTH_TOKEN", "TOK", f)
    assert f.read_text() == "# komentar\nA=1\nCLAUDE_CODE_OAUTH_TOKEN=TOK\nB=dua\n"
    save_env_var("BARU", "x", f)
    assert f.read_text().endswith("B=dua\nBARU=x\n")
    assert stat.S_IMODE(f.stat().st_mode) == 0o600


def test_save_env_var_ignores_commented_line_and_creates_file(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# CLAUDE_CODE_OAUTH_TOKEN=lama\n")
    save_env_var("CLAUDE_CODE_OAUTH_TOKEN", "BARU", f)
    assert f.read_text() == "# CLAUDE_CODE_OAUTH_TOKEN=lama\nCLAUDE_CODE_OAUTH_TOKEN=BARU\n"
    g = tmp_path / "baru" if False else tmp_path / ".env2"
    save_env_var("K", "v", g)
    assert g.read_text() == "K=v\n"


def test_run_setup_token_captures_output_through_a_real_pty(tmp_path):
    fake = tmp_path / "fake_claude.py"
    fake.write_text(textwrap.dedent(f'''
        import sys
        print("\\x1b[1mBuka tautan ...\\x1b[0m")
        print("Token (1 tahun):")
        import os
        print("kolom=%d" % os.get_terminal_size().columns)
        print("  {TOKEN}")
        print("Simpan baik-baik.")
    '''))
    launcher = tmp_path / "claude"
    launcher.write_text(f"#!/bin/sh\nexec {sys.executable} {fake}\n")
    launcher.chmod(0o755)
    code, raw = run_setup_token(launcher)
    assert code == 0 and extract_token(raw) == TOKEN
    assert "kolom=500" in raw                                    # CLI melihat terminal lebar: token tidak dipatahkan
