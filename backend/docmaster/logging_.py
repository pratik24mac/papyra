"""Structured, redacting logs: stderr (picked up by the desktop shell) plus a rotating file in the
app data dir. Email addresses, bearer-like tokens and long digit runs are masked before anything
is written; RPC params are never logged at all."""
from __future__ import annotations
import logging, re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_PATTERNS = [
    (re.compile(r"[\w.+\-']+@[\w\-]+(\.[\w\-]+)+"), "<email>"),
    (re.compile(r"(?i)(password|passwd|pwd|token|secret|authorization)(\W{0,3})([^\s,;'\"]{3,})"), r"\1\2<redacted>"),
    (re.compile(r"\b\d{10,}\b"), "<number>"),
]


def redact(text: str) -> str:
    for pat, rep in _PATTERNS:
        text = pat.sub(rep, text)
    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def configure(level: str = "INFO", data_dir: Path | None = None) -> Path | None:
    root = logging.getLogger()
    root.handlers.clear(); root.setLevel(level)
    fmt = RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    import sys
    h = logging.StreamHandler(sys.stderr); h.setFormatter(fmt); root.addHandler(h)
    if data_dir is None:
        return None
    logs = data_dir / "logs"; logs.mkdir(parents=True, exist_ok=True)
    fh = RotatingFileHandler(logs / "backend.log", maxBytes=1_000_000, backupCount=3, encoding="utf8")
    fh.setFormatter(fmt); root.addHandler(fh)
    return logs
