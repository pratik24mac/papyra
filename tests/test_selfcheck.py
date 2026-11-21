"""Engine self-check and the packaging guard."""
import subprocess, sys
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from docmaster import selfcheck  # noqa: E402
from docmaster.rpc.methods import build_methods  # noqa: E402
from docmaster.secrets.credential_store import CredentialStore  # noqa: E402


class Ctx:
    def progress(self, **k): pass


class FakeKeyring:
    d: dict = {}
    def set_password(self, s, k, v): self.d[(s, k)] = v
    def get_password(self, s, k): return self.d.get((s, k))
    def delete_password(self, s, k): self.d.pop((s, k), None)


def test_all_runtime_modules_present_here():
    assert selfcheck.missing_modules() == []


def test_missing_module_is_reported_with_a_fix(monkeypatch):
    monkeypatch.setattr(selfcheck, "RUNTIME_MODULES", ("docx", "definitely_not_installed_xyz"))
    checks = selfcheck.check_modules()
    bad = [c for c in checks if not c["ok"]]
    assert len(bad) == 1 and "definitely_not_installed_xyz" in bad[0]["check"] and "Rebuild" in bad[0]["fix"]
    assert selfcheck.missing_modules() == ["definitely_not_installed_xyz"]


def test_engine_refuses_to_start_without_its_modules(tmp_path):
    code = ("import sys; sys.path.insert(0, %r); import docmaster.selfcheck as s; s.RUNTIME_MODULES = ('nope_module',); "
            "from docmaster.__main__ import main; sys.exit(main(['--templates-dir', %r, '--output-dir', %r]))") % (str(ROOT / "backend"), str(ROOT / "templates"), str(tmp_path))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert r.returncode == 3 and "FATAL: engine packaged without required modules: nope_module" in r.stderr


def test_selfcheck_rpc_reports_conversion_and_log(tmp_path):
    from docmaster.pdfconv.libreoffice import find_soffice
    m = build_methods(ROOT / "templates", tmp_path / "out", data_dir=tmp_path / "data", credentials=CredentialStore(backend=FakeKeyring()))
    r = m["system.selfcheck"](Ctx(), convert=find_soffice() is not None)
    names = [c["check"] for c in r["checks"]]
    assert "module psutil" in names and "LibreOffice installed" in names
    if find_soffice():
        conv = next(c for c in r["checks"] if c["check"] == "Test PDF conversion")
        assert conv["ok"], conv
        assert r["ok"]
    assert r["log_path"].endswith("backend.log")


def test_crash_message_names_the_cause(tmp_path):
    from docmaster.rpc.server import Server
    sent = []
    class S(Server):
        def __init__(self): self.methods = {"boom": lambda ctx: (_ for _ in ()).throw(ModuleNotFoundError("No module named 'psutil'"))}
        def send(self, msg): sent.append(msg)
    S()._handle({"id": 1, "method": "boom", "params": {}})
    err = sent[0]["error"]
    assert err["data"]["code"] == "INTERNAL_ERROR" and "No module named 'psutil'" in err["message"] and err["data"]["type"] == "ModuleNotFoundError"
