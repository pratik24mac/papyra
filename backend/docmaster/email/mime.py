"""One MIME builder for every workflow: the .eml file and the IMAP draft are byte-identical
messages, built with the standard library (RFC 5322 headers, RFC 2047 encoding for Unicode
names and subjects, RFC 2231 attachment filenames, base64 attachment body)."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage
from email.utils import formatdate, getaddresses, make_msgid
from pathlib import Path
from ..errors import EmailAttachmentTooLarge, EmailInvalidAddress

# local part and domain may contain non-ASCII (EAI / IDN); no whitespace, brackets or multiple @
ADDR_RE = re.compile(r"^[^\s@<>,;\"]+@[^\s@<>,;\"]+\.[^\s@<>,;\".]{2,}$")
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024


def parse_recipients(value, field_name: str = "to") -> list[str]:
    """Accepts 'a@x.com, Name <b@y.org>; c@z.net' or a list. Returns 'Name <addr>' / 'addr' strings."""
    if value in (None, ""):
        return []
    items = value if isinstance(value, list) else re.split(r"[;,]", str(value))
    out = []
    for name, addr in getaddresses([i.strip() for i in items if i and i.strip()]):
        if not addr or not ADDR_RE.match(addr):
            raise EmailInvalidAddress(data={"field": field_name, "value": (addr or name)[:120]})
        out.append(f"{name} <{addr}>" if name else addr)
    return out


@dataclass
class DraftSpec:
    to: list[str]
    subject: str
    body: str
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    sender: str | None = None

    @staticmethod
    def from_dict(d: dict, sender: str | None = None) -> "DraftSpec":
        to = parse_recipients(d.get("to"), "to")
        if not to:
            raise EmailInvalidAddress("at least one recipient is required", data={"field": "to"})
        subject = str(d.get("subject") or "").strip()
        if not subject:
            raise EmailInvalidAddress("a subject is required", data={"field": "subject"})
        return DraftSpec(to=to, cc=parse_recipients(d.get("cc"), "cc"), bcc=parse_recipients(d.get("bcc"), "bcc"),
                         subject=subject, body=str(d.get("body") or ""), sender=sender)


def build_message(spec: DraftSpec, attachment: Path, unsent: bool = False) -> EmailMessage:
    size = attachment.stat().st_size
    if size > MAX_ATTACHMENT_BYTES:
        raise EmailAttachmentTooLarge(data={"bytes": size, "limit": MAX_ATTACHMENT_BYTES})
    msg = EmailMessage(policy=policy.SMTP)
    if spec.sender:
        msg["From"] = spec.sender
    msg["To"] = ", ".join(spec.to)
    if spec.cc: msg["Cc"] = ", ".join(spec.cc)
    if spec.bcc: msg["Bcc"] = ", ".join(spec.bcc)
    msg["Subject"] = spec.subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="papyra.local")
    if unsent:
        msg["X-Unsent"] = "1"           # Outlook opens such .eml files as editable, unsent messages
    msg.set_content(spec.body or "", subtype="plain", charset="utf-8")
    msg.add_attachment(attachment.read_bytes(), maintype="application", subtype="pdf", filename=attachment.name)
    return msg
