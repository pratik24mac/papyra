"""Workflow A: write the draft as an RFC 5322 .eml file next to the generated document."""
from __future__ import annotations
from email import message_from_bytes
from pathlib import Path
from ..errors import EmailDraftFailed
from ..storage.paths import unique_path
from .mime import DraftSpec, build_message


def write_eml(spec: DraftSpec, pdf: Path) -> Path:
    msg = build_message(spec, pdf, unsent=True)
    target = unique_path(pdf.parent, pdf.stem, ".eml")
    data = msg.as_bytes()
    target.write_bytes(data)
    parsed = message_from_bytes(target.read_bytes())        # verify it parses and the attachment survived
    atts = [p for p in parsed.walk() if p.get_content_disposition() == "attachment"]
    if not atts or atts[0].get_payload(decode=True) != pdf.read_bytes():
        target.unlink(missing_ok=True)
        raise EmailDraftFailed("the .eml file did not round-trip the attachment")
    return target
