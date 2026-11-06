"""Safe file naming inside app-managed directories. No path from the UI is ever used directly."""
from __future__ import annotations
import re
from datetime import date
from pathlib import Path
from ..errors import OutputPathError

_SAFE = re.compile(r"[^\w .()-]+", re.UNICODE)   # Unicode letters/digits allowed (Zoë, Müller); no slashes, colons, control chars
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_stem(raw: str, max_len: int = 80) -> str:
    s = _SAFE.sub("-", raw).strip(" .-")
    s = re.sub(r"[-\s]{2,}", "-", s)[:max_len].rstrip(" .-") or "document"
    return f"{s}_" if s.upper() in _RESERVED else s


def filename_from_pattern(pattern: str, values: dict, today: date | None = None) -> str:
    ctx = {k: str(v) for k, v in values.items() if isinstance(v, (str, int, float))}
    ctx["date"] = (today or date.today()).isoformat()
    try:
        return safe_stem(pattern.format(**ctx))
    except KeyError as e:
        raise OutputPathError(f"output filename pattern refers to unknown field {e}")


def ensure_dir(path: Path) -> Path:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-test"; probe.write_bytes(b""); probe.unlink()
    except OSError as e:
        raise OutputPathError(data={"path": str(path), "reason": str(e)})
    return path


def unique_path(directory: Path, stem: str, suffix: str) -> Path:
    """Never overwrite: name, name (2), name (3) …"""
    candidate = directory / f"{stem}{suffix}"
    n = 2
    while candidate.exists():
        candidate = directory / f"{stem} ({n}){suffix}"; n += 1
    return candidate
