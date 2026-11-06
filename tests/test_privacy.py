"""Privacy and offline guarantees: generation with networking disabled, offline mode, history,
log redaction, reachability diagnostics, privacy summary."""
import logging, shutil, socket, sys
from pathlib import Path
import pytest, yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from docmaster.docgen.render import render_docx  # noqa: E402
from docmaster.email import imap_draft  # noqa: E402
from docmaster.logging_ import redact, RedactingFormatter  # noqa: E402
from docmaster.net import OfflineMode, check_reachability  # noqa: E402
from docmaster.rpc.methods import build_methods  # noqa: E402
from docmaster.secrets.credential_store import CredentialStore  # noqa: E402
from docmaster.storage.history import History  # noqa: E402
from docmaster.storage.jobs import JobRecord, JobStore  # noqa: E402

TPL = ROOT / "templates/resume-ats/v1"
HAS_LO = Path("/Applications/LibreOffice.app").exists() or shutil.which("soffice")


class Ctx:
    def progress(self, **k): pass


class FakeKeyring:
    def __init__(self): self.d = {}
    def set_password(self, s, k, v): self.d[(s, k)] = v
    def get_password(self, s, k): return self.d.get((s, k))
    def delete_password(self, s, k): self.d.pop((s, k), None)


@pytest.fixture
def no_network(monkeypatch):
    """Any attempt to open a socket from Python fails loudly."""
    def boom(*a, **k): raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)


def test_document_generation_needs_no_network(tmp_path, no_network):
    schema = yaml.safe_load((TPL / "schema.yaml").read_text()); values = yaml.safe_load((TPL / "values.example.yaml").read_text())
    out = render_docx(TPL / "template.docx", schema, values, tmp_path / "o.docx")
    assert out.exists()
    if HAS_LO:
        m = build_methods(ROOT / "templates", tmp_path / "out", data_dir=tmp_path / "data", credentials=CredentialStore(backend=FakeKeyring()))
        r = m["docgen.generate"](Ctx(), template_id="resume-ats", values=values, job_id="offline-1")
        assert Path(r["pdf_path"]).exists() and r["pages"] == 2
        m["email.prepare_eml"](Ctx(), job_id="offline-1", message={"to": "a@b.co", "subject": "s", "body": "b"})
        assert m["history.list"](Ctx())["total"] == 1


def test_offline_mode_blocks_every_connection(tmp_path, no_network):
    m = build_methods(ROOT / "templates", tmp_path / "out", data_dir=tmp_path / "data", credentials=CredentialStore(backend=FakeKeyring()))
    m["settings.set"](Ctx(), key="imap_account", value={"email": "me@example.com", "host": "imap.example.com", "port": 993})
    assert m["settings.get"](Ctx())["offline_mode"] is True                      # default: offline
    with pytest.raises(OfflineMode): m["email.imap_test"](Ctx(), password="x")
    with pytest.raises(OfflineMode): m["network.check"](Ctx())
    m["settings.set"](Ctx(), key="offline_mode", value=False)
    with pytest.raises(AssertionError, match="network access attempted"):   # proves the guard, not the fake, was what blocked it
        m["email.imap_test"](Ctx(), password="x")


def test_history_records_and_deletes_with_files(tmp_path):
    h = History(tmp_path / "data")
    jd = tmp_path / "out" / "j1"; jd.mkdir(parents=True); (jd / "a.pdf").write_bytes(b"x")
    h.record_job("j1", "resume-ats", 1, "pdf_done", tmp_path / "out", jd / "a.docx", jd / "a.pdf", 2)
    h.record_draft("j1", "imap", "saved", "Drafts")
    rows = h.list(); assert rows[0]["job_id"] == "j1" and rows[0]["drafts"] == 1 and rows[0]["pdf_exists"] and not rows[0]["docx_exists"]
    assert h.delete("j1", delete_files=False) == {"job_id": "j1", "removed_row": True, "removed_files": False} and jd.exists()
    h.record_job("j1", "resume-ats", 1, "pdf_done", tmp_path / "out", jd / "a.docx", jd / "a.pdf", 2)
    assert h.delete("j1", delete_files=True)["removed_files"] and not jd.exists() and h.count() == 0
    h.record_job("j2", "t", 1, "pdf_done", tmp_path / "out"); assert h.clear(False)["removed_rows"] == 1 and h.count() == 0
    with pytest.raises(Exception):                    # job ids are validated before touching the filesystem
        build_methods(ROOT / "templates", tmp_path / "out", data_dir=tmp_path / "data2", credentials=CredentialStore(backend=FakeKeyring()))["history.delete"](Ctx(), job_id="../x", delete_files=True)


def test_history_opt_out(tmp_path, no_network):
    if not HAS_LO: pytest.skip("LibreOffice not installed")
    m = build_methods(ROOT / "templates", tmp_path / "out", data_dir=tmp_path / "data", credentials=CredentialStore(backend=FakeKeyring()))
    m["settings.set"](Ctx(), key="keep_history", value=False)
    values = yaml.safe_load((TPL / "values.example.yaml").read_text())
    m["docgen.generate"](Ctx(), template_id="resume-ats", values=values, job_id="nohist")
    assert m["history.list"](Ctx())["total"] == 0 and (tmp_path / "out" / "nohist" / "job.json").exists()


def test_log_redaction():
    assert redact("draft for zoe.muller+x@example.co.uk saved") == "draft for <email> saved"
    assert redact("password=SuperSecret123 token: abcdef") == "password=<redacted> token: <redacted>"
    assert redact("phone 9876543210 and id 42") == "phone <number> and id 42"
    rec = logging.LogRecord("x", logging.INFO, "", 0, "login %s failed", ("me@porkbun.example",), None)
    assert "<email>" in RedactingFormatter("%(message)s").format(rec) and "porkbun" not in RedactingFormatter("%(message)s").format(rec)


def test_reachability_reports_each_stage(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: (_ for _ in ()).throw(socket.gaierror(8, "nodename nor servname provided")))
    r = check_reachability("imap.example.invalid", 993)
    assert r["dns"]["ok"] is False and r["tcp"] is None and r["ok"] is False
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("203.0.113.5", 993))])
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(TimeoutError("timed out")))
    r = check_reachability("imap.example.com", 993, timeout=0.1)
    assert r["dns"]["ok"] and r["dns"]["addresses"] == ["203.0.113.5"] and r["tcp"]["ok"] is False and "TimeoutError" in r["tcp"]["error"]


def test_privacy_summary_lists_everything(tmp_path):
    m = build_methods(ROOT / "templates", tmp_path / "out", data_dir=tmp_path / "data", credentials=CredentialStore(backend=FakeKeyring()))
    s = m["privacy.summary"](Ctx())
    assert s["telemetry"] is False and s["outbound"] == [] and s["offline_mode"] is True      # offline by default
    assert {x["what"].split(" ")[0] for x in s["stored"]} == {"Generated", "Document", "Settings", "Mailbox", "Logs"}
    m["settings.set"](Ctx(), key="imap_account", value={"email": "me@example.com", "host": "imap.porkbun.com", "port": 993})
    s = m["privacy.summary"](Ctx())
    assert s["outbound"] == [{"purpose": "Save email drafts to your mailbox (IMAP over TLS)", "host": "imap.porkbun.com", "port": 993, "when": "only when you click Create draft"}]
    assert m["privacy.cleanup"](Ctx())["removed_partial_files"] == 0 and m["privacy.clear_logs"](Ctx())["cleared"] == 0


def test_socket_guard_blocks_raw_connections_while_offline(tmp_path):
    """Even code that bypasses the IMAP module cannot open a TCP connection while offline."""
    from docmaster import net
    m = build_methods(ROOT / "templates", tmp_path / "out", data_dir=tmp_path / "data", credentials=CredentialStore(backend=FakeKeyring()))
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        with pytest.raises(OfflineMode):
            s.connect(("127.0.0.1", 9))
        s.close()
        m["settings.set"](Ctx(), key="offline_mode", value=False)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(0.2)
        with pytest.raises(OSError) as e:                                        # guard lifted: a real (refused) connect happens
            s.connect(("127.0.0.1", 9))
        assert not isinstance(e.value, OfflineMode)
        s.close()
    finally:
        net.uninstall_guard()
