"""Workflow D: append the draft to the user's Drafts folder over IMAP (Porkbun, Fastmail, any
standard provider). Nothing is ever sent: APPEND stores the message, the user sends it from their
own mail client after review."""
from __future__ import annotations
import imaplib, re, socket, ssl, time
from dataclasses import dataclass
from email.message import EmailMessage
from ..errors import EmailAuthFailed, EmailImapError, EmailNetworkError
from ..net import OfflineMode

DRAFT_NAMES = ("Drafts", "INBOX.Drafts", "INBOX/Drafts", "[Gmail]/Drafts", "Draft")


@dataclass
class ImapAccount:
    email: str
    host: str
    port: int = 993
    username: str | None = None
    drafts_folder: str | None = None

    @staticmethod
    def from_dict(d: dict) -> "ImapAccount":
        email = str(d.get("email") or "").strip(); host = str(d.get("host") or "").strip()
        if not email or "@" not in email or not host:
            raise EmailImapError("email address and IMAP host are required", data={"field": "account"})
        port = int(d.get("port") or 993)
        if not 1 <= port <= 65535:
            raise EmailImapError("invalid port", data={"field": "port"})
        return ImapAccount(email=email, host=host, port=port, username=(d.get("username") or "").strip() or None,
                           drafts_folder=(d.get("drafts_folder") or "").strip() or None)

    def public(self) -> dict:
        return {"email": self.email, "host": self.host, "port": self.port, "username": self.username or self.email, "drafts_folder": self.drafts_folder}


OFFLINE = {"enabled": False}      # set by the methods layer from settings before any connection


def _connect(account: ImapAccount, password: str, timeout: float = 20.0, factory=None):
    if OFFLINE["enabled"]:
        raise OfflineMode()
    factory = factory or imaplib.IMAP4_SSL
    try:
        conn = factory(account.host, account.port, ssl_context=ssl.create_default_context(), timeout=timeout)
    except (socket.gaierror, socket.timeout, TimeoutError, ConnectionError, OSError) as e:
        raise EmailNetworkError(data={"host": account.host, "reason": type(e).__name__})
    try:
        conn.login(account.username or account.email, password)
    except imaplib.IMAP4.error as e:
        try: conn.logout()
        except Exception: pass  # noqa: BLE001
        raise EmailAuthFailed(data={"host": account.host, "reason": str(e)[:200]})
    return conn


def find_drafts_folder(conn) -> str:
    typ, lines = conn.list()
    if typ != "OK":
        raise EmailImapError("LIST failed", data={"reason": str(lines)[:200]})
    names = []
    for raw in lines or []:
        line = raw.decode("utf8", "replace") if isinstance(raw, bytes) else str(raw)
        m = re.match(r'\((?P<flags>[^)]*)\)\s+(?P<delim>"[^"]*"|NIL)\s+(?P<name>"(?:[^"\\]|\\.)*"|\S+)', line)
        if not m:
            continue
        name = m.group("name").strip('"')
        if "\\drafts" in m.group("flags").lower():
            return name                                   # RFC 6154 special-use wins
        names.append(name)
    for cand in DRAFT_NAMES:
        if cand in names:
            return cand
    for n in names:
        if n.lower().endswith("drafts"):
            return n
    raise EmailImapError("no Drafts folder found on the server", data={"folders": names[:30]})


def test_connection(account: ImapAccount, password: str, factory=None) -> dict:
    conn = _connect(account, password, factory=factory)
    try:
        folder = account.drafts_folder or find_drafts_folder(conn)
        typ, _ = conn.select(_quote(folder), readonly=True)
        if typ != "OK":
            raise EmailImapError(f"cannot open folder {folder}", data={"folder": folder})
        return {"ok": True, "drafts_folder": folder}
    finally:
        try: conn.logout()
        except Exception: pass  # noqa: BLE001


def append_draft(account: ImapAccount, password: str, msg: EmailMessage, factory=None) -> dict:
    conn = _connect(account, password, factory=factory)
    try:
        folder = account.drafts_folder or find_drafts_folder(conn)
        typ, data = conn.append(_quote(folder), r"(\Draft \Seen)", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
        if typ != "OK":
            raise EmailImapError("APPEND was rejected", data={"folder": folder, "reason": str(data)[:200]})
        text = data[0].decode("utf8", "replace") if data and isinstance(data[0], bytes) else str(data[0] if data else "")
        m = re.search(r"APPENDUID (\d+) (\d+)", text)
        return {"folder": folder, "uid": int(m.group(2)) if m else None, "confirmed": True}
    finally:
        try: conn.logout()
        except Exception: pass  # noqa: BLE001


def _quote(folder: str) -> str:
    return folder if folder.startswith('"') else '"' + folder.replace("\\", "\\\\").replace('"', '\\"') + '"'
