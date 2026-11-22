"""Email workflows: MIME construction, .eml round-trip, IMAP draft with a fake server,
credential store chunking, and the RPC methods end to end (no network)."""
import imaplib, shutil, sys
from email import message_from_bytes, policy
from pathlib import Path
import pytest, yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from docmaster.email.mime import DraftSpec, build_message, parse_recipients  # noqa: E402
from docmaster.email.eml import write_eml  # noqa: E402
from docmaster.email import imap_draft  # noqa: E402
from docmaster.errors import EmailInvalidAddress, EmailAuthFailed, EmailNetworkError, EmailImapError, EmailAccountMissing, PdfStale  # noqa: E402
from docmaster.secrets.credential_store import CredentialStore  # noqa: E402
from docmaster.rpc.methods import build_methods  # noqa: E402
from docmaster.storage.jobs import JobRecord, JobStore  # noqa: E402

PDF = ROOT / "templates/resume-ats/v1/samples/example-output.pdf"
DOCX = ROOT / "templates/resume-ats/v1/samples/example-output.docx"


class Ctx:
    def progress(self, **k): pass


class FakeKeyring:
    def __init__(self): self.d = {}
    def set_password(self, s, k, v): self.d[(s, k)] = v
    def get_password(self, s, k): return self.d.get((s, k))
    def delete_password(self, s, k): self.d.pop((s, k), None)


class FakeImap:
    """Just enough of imaplib.IMAP4_SSL for the draft flow."""
    instances = []
    password = "secret-pw"
    folders = [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\Drafts) "/" "Drafts"', b'(\\HasNoChildren) "/" "Sent"']
    fail_connect = False

    def __init__(self, host, port, ssl_context=None, timeout=None):
        if FakeImap.fail_connect: raise OSError("unreachable")
        self.host, self.port, self.appended, self.logged_out = host, port, [], False
        FakeImap.instances.append(self)
    def login(self, user, pw):
        if pw != FakeImap.password: raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Authentication failed.")
        self.user = user
    def list(self): return "OK", list(FakeImap.folders)
    def select(self, folder, readonly=False): return ("OK", [b"3"]) if folder == '"Drafts"' else ("NO", [b"no such folder"])
    def append(self, folder, flags, date, data):
        self.appended.append((folder, flags, data)); return "OK", [b"[APPENDUID 1234 57] Append completed."]
    def logout(self): self.logged_out = True


def test_recipient_parsing():
    assert parse_recipients("a@x.com, Zoë <zoe@müller.example>; c@z.net") == ["a@x.com", "Zoë <zoe@müller.example>", "c@z.net"]
    assert parse_recipients(["x@y.io"]) == ["x@y.io"] and parse_recipients("") == []
    with pytest.raises(EmailInvalidAddress): parse_recipients("not-an-address")
    with pytest.raises(EmailInvalidAddress): DraftSpec.from_dict({"to": "", "subject": "s"})
    with pytest.raises(EmailInvalidAddress): DraftSpec.from_dict({"to": "a@b.co", "subject": " "})


def test_mime_round_trip_unicode_and_attachment():
    spec = DraftSpec.from_dict({"to": "hr@example.com", "cc": "Zoë Müller <zoe@example.com>", "bcc": "me@example.com",
                                "subject": "Résumé — Zoë Müller-Łukasz ☐", "body": "Dear Hiring Manager,\n\nПривет — 日本語\n"}, sender="me@porkbun.example")
    msg = build_message(spec, PDF, unsent=True)
    parsed = message_from_bytes(msg.as_bytes(), policy=policy.default)
    assert parsed["Subject"] == "Résumé — Zoë Müller-Łukasz ☐" and parsed["From"] == "me@porkbun.example"
    assert parsed["Cc"] == "Zoë Müller <zoe@example.com>" and parsed["X-Unsent"] == "1" and parsed["Message-ID"]
    parts = list(parsed.walk())
    body = next(p for p in parts if p.get_content_type() == "text/plain")
    assert "Привет — 日本語" in body.get_payload(decode=True).decode("utf8")
    att = next(p for p in parts if p.get_content_disposition() == "attachment")
    assert att.get_content_type() == "application/pdf" and att.get_filename() == PDF.name
    assert att.get_payload(decode=True) == PDF.read_bytes()


def test_eml_written_and_verified(tmp_path):
    pdf = tmp_path / "Doc.pdf"; shutil.copy(PDF, pdf)
    spec = DraftSpec.from_dict({"to": "hr@example.com", "subject": "Hi", "body": "x"})
    p = write_eml(spec, pdf)
    assert p == tmp_path / "Doc.eml" and p.stat().st_size > PDF.stat().st_size
    assert write_eml(spec, pdf) == tmp_path / "Doc (2).eml"             # never overwrite


def test_imap_append_uses_special_use_drafts_folder():
    FakeImap.instances.clear()
    acct = imap_draft.ImapAccount.from_dict({"email": "me@example.com", "host": "imap.porkbun.com"})
    assert acct.port == 993
    assert imap_draft.test_connection(acct, "secret-pw", factory=FakeImap) == {"ok": True, "drafts_folder": "Drafts"}
    msg = build_message(DraftSpec.from_dict({"to": "a@b.co", "subject": "s", "body": "b"}, sender=acct.email), PDF)
    res = imap_draft.append_draft(acct, "secret-pw", msg, factory=FakeImap)
    assert res == {"folder": "Drafts", "uid": 57, "confirmed": True}
    conn = FakeImap.instances[-1]
    assert conn.appended[0][0] == '"Drafts"' and conn.appended[0][1] == r"(\Draft \Seen)" and b"application/pdf" in conn.appended[0][2]
    assert conn.logged_out and conn.user == "me@example.com"


def test_imap_folder_fallbacks_and_errors():
    FakeImap.folders = [b'(\\HasNoChildren) "." "INBOX"', b'(\\HasNoChildren) "." "INBOX.Drafts"']
    acct = imap_draft.ImapAccount.from_dict({"email": "me@example.com", "host": "h", "port": "993"})
    conn = FakeImap("h", 993); conn.login("me@example.com", "secret-pw")
    assert imap_draft.find_drafts_folder(conn) == "INBOX.Drafts"
    FakeImap.folders = [b'(\\HasNoChildren) "/" "INBOX"']
    with pytest.raises(EmailImapError): imap_draft.find_drafts_folder(FakeImap("h", 993))
    with pytest.raises(EmailAuthFailed): imap_draft.test_connection(acct, "wrong", factory=FakeImap)
    FakeImap.fail_connect = True
    with pytest.raises(EmailNetworkError): imap_draft.test_connection(acct, "secret-pw", factory=FakeImap)
    FakeImap.fail_connect = False
    FakeImap.folders = [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\Drafts) "/" "Drafts"', b'(\\HasNoChildren) "/" "Sent"']
    with pytest.raises(EmailImapError): imap_draft.ImapAccount.from_dict({"email": "x", "host": "h"})


def test_credential_store_chunks_long_secrets():
    kr = FakeKeyring(); store = CredentialStore(backend=kr)
    secret = "t" * 2600                                   # longer than Windows' 2560-byte limit
    store.set("imap:me@example.com", secret)
    assert store.get("imap:me@example.com") == secret and len(kr.d) == 4   # count + 3 chunks
    store.delete("imap:me@example.com")
    assert store.get("imap:me@example.com") is None and kr.d == {}


def test_email_methods_end_to_end(tmp_path):
    kr = FakeKeyring()
    m = build_methods(ROOT / "templates", tmp_path / "out", data_dir=tmp_path / "data", credentials=CredentialStore(backend=kr), imap_factory=FakeImap)
    # a finished job on disk
    jd = tmp_path / "out" / "job-e"; jd.mkdir(parents=True)
    docx, pdf = jd / "Doc.docx", jd / "Doc.pdf"; shutil.copy(DOCX, docx); shutil.copy(PDF, pdf)
    rec = JobRecord.new("job-e", "resume-ats", 1, docx, None); rec.set_pdf(pdf, 2); JobStore(tmp_path / "out").save(rec)
    msg = {"to": "hr@example.com", "subject": "Application", "body": "Hello"}
    # .eml
    r = m["email.prepare_eml"](Ctx(), job_id="job-e", message=msg)
    assert Path(r["eml_path"]).exists() and r["attachment"] == "Doc.pdf"
    assert m["jobs.get"](Ctx(), job_id="job-e")["job"]["drafts"][0]["mode"] == "eml"
    # offline by default: the mailbox is unreachable until the user turns offline mode off
    with pytest.raises(Exception) as e:
        m["email.imap_save_account"](Ctx(), account={"email": "me@example.com", "host": "imap.porkbun.com"}, password="secret-pw")
    assert e.value.code == "OFFLINE_MODE"
    m["settings.set"](Ctx(), key="offline_mode", value=False)
    # no account yet
    assert m["email.imap_get_account"](Ctx()) == {"configured": False}
    with pytest.raises(EmailAccountMissing): m["email.create_imap_draft"](Ctx(), job_id="job-e", message=msg)
    # wrong password is rejected before anything is stored
    with pytest.raises(EmailAuthFailed):
        m["email.imap_save_account"](Ctx(), account={"email": "me@example.com", "host": "imap.porkbun.com"}, password="wrong")
    assert kr.d == {} and not m["email.imap_get_account"](Ctx())["configured"]
    acct = m["email.imap_save_account"](Ctx(), account={"email": "me@example.com", "host": "imap.porkbun.com"}, password="secret-pw")
    assert acct["configured"] and acct["has_password"] and acct["drafts_folder"] == "Drafts" and "secret-pw" not in str(acct)
    assert "secret-pw" not in (tmp_path / "data" / "settings.json").read_text()        # password only in the credential store
    r = m["email.create_imap_draft"](Ctx(), job_id="job-e", message=msg)
    assert r["confirmed"] and r["folder"] == "Drafts" and r["account"] == "me@example.com"
    drafts = m["jobs.get"](Ctx(), job_id="job-e")["job"]["drafts"]
    assert [d["mode"] for d in drafts] == ["eml", "imap"]
    # stale PDF blocks both workflows
    docx.write_bytes(docx.read_bytes() + b"\n")
    with pytest.raises(PdfStale): m["email.prepare_eml"](Ctx(), job_id="job-e", message=msg)
    with pytest.raises(PdfStale): m["email.create_imap_draft"](Ctx(), job_id="job-e", message=msg)
    assert m["email.imap_remove_account"](Ctx()) == {"configured": False} and kr.d == {}


def test_eml_and_mime_with_several_attachments(tmp_path):
    pdf1 = tmp_path / "A.pdf"; pdf2 = tmp_path / "B.pdf"; shutil.copy(PDF, pdf1); shutil.copy(PDF, pdf2)
    spec = DraftSpec.from_dict({"to": "hr@example.com", "subject": "Two docs", "body": "x"})
    msg = build_message(spec, [pdf1, pdf2])
    atts = [p for p in message_from_bytes(msg.as_bytes()).walk() if p.get_content_disposition() == "attachment"]
    assert [a.get_filename() for a in atts] == ["A.pdf", "B.pdf"]
    out = write_eml(spec, [pdf1, pdf2])
    assert out.name == "A (+1 more).eml" and out.stat().st_size > 2 * PDF.stat().st_size
