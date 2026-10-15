import os
from pathlib import Path

import pytest

from chunai.sandbox import isolation_available, run_python

pytestmark = pytest.mark.skipif(not isolation_available(), reason="unshare -rn tidak tersedia")


@pytest.fixture
def ws(tmp_path):
    (tmp_path / "masukan").mkdir()
    (tmp_path / "masukan" / "d.csv").write_text("x,y\n1,2\n3,4\n")
    return tmp_path


def test_pandas_and_chart_work_and_report_new_files(ws):
    r = run_python("import pandas as pd, matplotlib.pyplot as plt\n"
                   "d = pd.read_csv('masukan/d.csv'); print(d.y.sum())\n"
                   "import os; os.makedirs('grafik', exist_ok=True)\n"
                   "d.plot(x='x', y='y'); plt.savefig('grafik/a.png')", ws)
    assert r.ok and r.stdout.strip() == "6" and "grafik/a.png" in r.new_files, r


def test_network_is_blocked(ws):
    r = run_python("import urllib.request\nurllib.request.urlopen('http://1.1.1.1', timeout=3)", ws)
    assert not r.ok and ("Diblokir" in r.stderr or "Errno" in r.stderr or "Error" in r.stderr)


def test_write_outside_workspace_blocked(ws, tmp_path_factory):
    other = tmp_path_factory.mktemp("lain") / "x.txt"
    r = run_python(f"open({str(other)!r}, 'w').write('x')", ws)
    assert not r.ok and "luar workspace" in r.stderr and not other.exists()


def test_delete_outside_workspace_blocked(ws, tmp_path_factory):
    victim = tmp_path_factory.mktemp("korban") / "penting.txt"
    victim.write_text("jangan hapus")
    r = run_python(f"import os\nos.remove({str(victim)!r})", ws)
    assert not r.ok and victim.exists()


def test_read_outside_workspace_and_secrets_blocked(ws, tmp_path_factory):
    secret = tmp_path_factory.mktemp("lain") / "rahasia.txt"
    secret.write_text("kunci")
    r = run_python(f"print(open({str(secret)!r}).read())", ws)
    assert not r.ok and "kunci" not in r.stdout
    r = run_python("print(open('/root/.ssh/id_rsa').read())", ws)
    assert not r.ok


def test_subprocess_and_os_system_blocked(ws):
    assert not run_python("import subprocess\nsubprocess.run(['echo','hi'])", ws).ok
    assert not run_python("import os\nos.system('echo hi')", ws).ok


def test_env_is_scrubbed(ws, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-rahasia")
    monkeypatch.setenv("CHUNAI_WEB_TOKEN", "tok")
    r = run_python("import os\nprint(os.environ.get('ANTHROPIC_API_KEY'), os.environ.get('CHUNAI_WEB_TOKEN'))", ws)
    assert r.ok and r.stdout.strip() == "None None"


def test_timeout_kills_process(ws):
    r = run_python("while True: pass", ws, timeout=2)
    assert r.timed_out and not r.ok


def test_memory_limit(ws):
    r = run_python("x = bytearray(4 * 1024**3)", ws, mem_mb=512)
    assert not r.ok


def test_syntax_error_reported(ws):
    r = run_python("def (", ws)
    assert not r.ok and "SyntaxError" in r.stderr
