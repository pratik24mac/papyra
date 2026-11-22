"""Workflow A: write the draft as an RFC 5322 .eml file next to the generated document."""
from __future__ import annotations
from email import message_from_bytes
from pathlib import Path
from ..errors import EmailDraftFailed
from ..storage.paths import unique_path
from .mime import DraftSpec, build_message


def write_eml(spec: DraftSpec, pdf: Path | list[Path]) -> Path:
    pdfs = [pdf] if isinstance(pdf, Path) else list(pdf)
    msg = build_message(spec, pdfs, unsent=True)
    stem = pdfs[0].stem if len(pdfs) == 1 else f"{pdfs[0].stem} (+{len(pdfs) - 1} more)"
    target = unique_path(pdfs[0].parent, stem, ".eml")
    target.write_bytes(msg.as_bytes())
    parsed = message_from_bytes(target.read_bytes())        # verify it parses and every attachment survived
    atts = [p.get_payload(decode=True) for p in parsed.walk() if p.get_content_disposition() == "attachment"]
    if len(atts) != len(pdfs) or any(a != p.read_bytes() for a, p in zip(atts, pdfs)):
        target.unlink(missing_ok=True)
        raise EmailDraftFailed("the .eml file did not round-trip the attachments")
    return target
