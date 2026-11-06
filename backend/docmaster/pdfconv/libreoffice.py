"""DOCX → PDF through LibreOffice headless, as the app will ship it.

* locate soffice (explicit override → platform defaults → PATH)
* one conversion at a time (process-wide lock), isolated user profile per run, hard timeout
* stdout/stderr captured for diagnostics, never shown raw to users
* the PDF is validated (exists, non-empty, parseable, page count, essential text) before it is
  moved next to the DOCX; on any failure the DOCX stays where it is
"""
from __future__ import annotations
import os, shutil, subprocess, sys, tempfile, threading, time
from pathlib import Path
from pypdf import PdfReader
from ..errors import LibreOfficeNotFound, PdfConversionFailed, PdfInvalid

_LOCK = threading.Lock()
_DEFAULTS = {
    "darwin": ["/Applications/LibreOffice.app/Contents/MacOS/soffice"],
    "win32": [r"C:\Program Files\LibreOffice\program\soffice.exe", r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"],
    "linux": ["/usr/bin/soffice", "/usr/bin/libreoffice", "/snap/bin/libreoffice"],
}


def find_soffice(override: str | None = None) -> Path | None:
    candidates = ([override] if override else []) + _DEFAULTS.get(sys.platform, []) + [shutil.which("soffice") or ""]
    return next((Path(c) for c in candidates if c and Path(c).exists()), None)


def soffice_version(soffice: Path) -> str | None:
    try:
        return subprocess.run([str(soffice), "--version"], capture_output=True, text=True, timeout=30).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def convert_to_pdf(docx: Path, soffice: Path | None = None, timeout: float = 120.0) -> tuple[Path, float]:
    soffice = soffice or find_soffice()
    if soffice is None:
        raise LibreOfficeNotFound()
    with _LOCK, tempfile.TemporaryDirectory(prefix="docmaster-lo-") as tmp:
        tmp = Path(tmp); profile = tmp / "profile"; outdir = tmp / "out"; outdir.mkdir()
        cmd = [str(soffice), "--headless", "--norestore", "--nologo", "--nolockcheck",
               f"-env:UserInstallation={profile.as_uri()}", "--convert-to", "pdf:writer_pdf_Export",
               "--outdir", str(outdir), str(docx)]
        t0 = time.monotonic()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env={**os.environ, "SAL_USE_VCLPLUGIN": "svp"})
        except subprocess.TimeoutExpired:
            raise PdfConversionFailed(f"LibreOffice did not finish within {timeout:.0f} s", data={"docx_path": str(docx)})
        except OSError as e:
            raise PdfConversionFailed(f"could not start LibreOffice: {e}", data={"docx_path": str(docx)})
        produced = outdir / (docx.stem + ".pdf")
        if proc.returncode != 0 or not produced.exists() or produced.stat().st_size == 0:
            raise PdfConversionFailed(data={"docx_path": str(docx), "exit_code": proc.returncode,
                                            "stderr": proc.stderr[-2000:], "stdout": proc.stdout[-500:]})
        final = docx.with_suffix(".pdf")
        shutil.move(str(produced), final)
        return final, time.monotonic() - t0


def validate_pdf(pdf: Path, expected_pages: dict | None = None, essential_text: list[str] | None = None) -> int:
    try:
        reader = PdfReader(pdf)
        pages = len(reader.pages)
        text = "\n".join(p.extract_text() or "" for p in reader.pages) if essential_text else ""
    except Exception as e:  # noqa: BLE001
        raise PdfInvalid(f"the PDF cannot be parsed: {type(e).__name__}", data={"pdf_path": str(pdf)})
    if pages == 0:
        raise PdfInvalid("the PDF has no pages", data={"pdf_path": str(pdf)})
    if expected_pages and not (expected_pages.get("min", 1) <= pages <= expected_pages.get("max", 10**6)):
        raise PdfInvalid(f"unexpected page count {pages}", data={"pdf_path": str(pdf), "pages": pages, "expected": expected_pages})
    norm = lambda s: " ".join(s.casefold().split())        # templates may upper-case or re-wrap values
    haystack = norm(text)
    missing = [t for t in (essential_text or []) if t and norm(t) not in haystack]
    if missing:
        raise PdfInvalid("essential text is missing from the PDF", data={"pdf_path": str(pdf), "missing": missing})
    return pages
