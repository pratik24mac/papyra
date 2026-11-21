"""Date formatting for printed documents. Values are stored as ISO (YYYY-MM-DD); the document
gets a formatted string. Portable token format (no platform-specific strftime flags):

  D   day (12)      DD  day, two digits (05)      Do  ordinal (12th)
  M   month (3)     MM  month, two digits (03)    MMM Mar    MMMM March
  YY  26            YYYY 2026                     dddd Thursday   ddd Thu

A `%` in the format switches to Python strftime for people who prefer it.
Resolution order for a field: field `format` → template `date_format` → the app setting → default.
"""
from __future__ import annotations
import re
from datetime import date

DEFAULT_FORMAT = "D MMMM YYYY"
PRESETS = ["D MMMM YYYY", "Do MMMM YYYY", "MMMM D, YYYY", "MMMM Do, YYYY", "DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD", "DD-MMM-YYYY", "dddd, D MMMM YYYY", "dddd, MMMM Do, YYYY"]
_TOKEN = re.compile(r"dddd|ddd|DD|Do|D|MMMM|MMM|MM|M|YYYY|YY")


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def format_date(iso: str, fmt: str | None = None) -> str:
    d = date.fromisoformat(iso)
    fmt = fmt or DEFAULT_FORMAT
    if "%" in fmt:
        return d.strftime(fmt.replace("%-d", str(d.day)).replace("%#d", str(d.day)).replace("%-m", str(d.month)).replace("%#m", str(d.month)))
    rep = {"D": str(d.day), "DD": f"{d.day:02d}", "Do": _ordinal(d.day), "M": str(d.month), "MM": f"{d.month:02d}",
           "MMM": d.strftime("%b"), "MMMM": d.strftime("%B"), "YY": f"{d.year % 100:02d}", "YYYY": str(d.year),
           "ddd": d.strftime("%a"), "dddd": d.strftime("%A")}
    return _TOKEN.sub(lambda m: rep[m.group(0)], fmt)


def check_format(fmt: str) -> str:
    """Raise ValueError for a format that produces nothing useful."""
    out = format_date("2026-03-12", fmt)
    if not out or out == fmt and not _TOKEN.search(fmt) and "%" not in fmt:
        raise ValueError(f"'{fmt}' contains no date tokens")
    return out


class FormattedDate(str):
    """The printed string, still carrying the ISO value so `{{ x | date("…") }}` can re-format it."""
    iso: str

    def __new__(cls, text: str, iso: str):
        obj = super().__new__(cls, text); obj.iso = iso
        return obj


def date_filter(value, fmt: str = DEFAULT_FORMAT) -> str:
    iso = getattr(value, "iso", None) or (value if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else None)
    if not iso:
        return str(value)
    return format_date(iso, fmt)
