"""DOCX → PDF through LibreOffice headless, as the app will ship it.

* locate soffice (explicit override → platform defaults → PATH)
* one conversion at a time (process-wide lock), hard timeout
* **persistent user profile** in the app data dir (`configure(profile_dir)`): LibreOffice's
  first-start work (font cache, registry, extensions) is paid once per installation, not per
  document. On a slow Windows PC that work alone takes minutes; with a warm profile a
  two-page document converts in seconds. The profile is private to Papyra (never the user's
  own LibreOffice settings), pre-seeded with the online update check disabled, warmed in the
  background at engine start, and rebuilt automatically if a conversion fails.
* stdout/stderr captured for diagnostics, never shown raw to users
* the PDF is validated (exists, non-empty, parseable, page count, essential text) before it is
  moved next to the DOCX; on any failure the DOCX stays where it is
"""
from __future__ import annotations
import logging, os, shutil, subprocess, sys, tempfile, threading, time
from pathlib import Path
from pypdf import PdfReader
from ..errors import LibreOfficeNotFound, PdfConversionFailed, PdfInvalid

log = logging.getLogger("docmaster.pdfconv")
_LOCK = threading.Lock()
_DEFAULTS = {
    "darwin": ["/Applications/LibreOffice.app/Contents/MacOS/soffice"],
    "win32": [r"C:\Program Files\LibreOffice\program\soffice.exe", r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"],
    "linux": ["/usr/bin/soffice", "/usr/bin/libreoffice", "/snap/bin/libreoffice"],
}
WARM_TIMEOUT = 900.0      # first start on a slow machine: font cache + registry + antivirus scan
CONVERT_TIMEOUT = 180.0   # a warm profile converts a normal document in seconds
WARM_MARKER = ".papyra-warm"
# Pre-seeded settings: no update check, no first-run wizard, no crash-report dialogs.
_SEED_XCU = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<item oor:path="/org.openoffice.Office.Jobs/Jobs/org.openoffice.Office.Jobs:Job['UpdateCheck']/Arguments"><prop oor:name="AutoCheckEnabled" oor:op="fuse"><value>false</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Misc"><prop oor:name="FirstRun" oor:op="fuse"><value>false</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Misc"><prop oor:name="ShowTipOfTheDay" oor:op="fuse"><value>false</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Misc"><prop oor:name="CrashReport" oor:op="fuse"><value>false</value></prop></item>
</oor:items>
"""

_profile_dir: Path | None = None   # set by configure(); None → temporary profile per conversion (tests)


def configure(profile_dir: Path | None) -> None:
    global _profile_dir
    _profile_dir = profile_dir


def find_soffice(override: str | None = None) -> Path | None:
    candidates = ([override] if override else []) + _DEFAULTS.get(sys.platform, []) + [shutil.which("soffice") or ""]
    return next((Path(c) for c in candidates if c and Path(c).exists()), None)


def soffice_version(soffice: Path) -> str | None:
    try:
        return subprocess.run([str(soffice), "--version"], capture_output=True, text=True, timeout=30).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def profile_is_warm(profile_dir: Path | None = None) -> bool:
    p = profile_dir or _profile_dir
    return bool(p) and (p / WARM_MARKER).exists()


def _seed_profile(profile: Path) -> None:
    user = profile / "user"
    user.mkdir(parents=True, exist_ok=True)
    xcu = user / "registrymodifications.xcu"
    if not xcu.exists():
        xcu.write_text(_SEED_XCU, encoding="utf8")


def reset_profile(profile_dir: Path | None = None) -> None:
    p = profile_dir or _profile_dir
    if p and p.exists():
        shutil.rmtree(p, ignore_errors=True)
        log.info("LibreOffice profile reset")


def _run(soffice: Path, docx: Path, profile: Path, outdir: Path, timeout: float) -> subprocess.CompletedProcess:
    _seed_profile(profile)
    cmd = [str(soffice), "--headless", "--norestore", "--nologo", "--nolockcheck", "--nodefault",
           f"-env:UserInstallation={profile.as_uri()}", "--convert-to", "pdf:writer_pdf_Export",
           "--outdir", str(outdir), str(docx)]
    env = {**os.environ, "SAL_USE_VCLPLUGIN": "svp"}
    creation = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if sys.platform == "win32" else {}
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, **creation)


def _convert_once(soffice: Path, docx: Path, profile: Path, timeout: float) -> tuple[Path, float]:
    """One attempt. Returns (temp pdf path, seconds); raises PdfConversionFailed."""
    outdir = Path(tempfile.mkdtemp(prefix="docmaster-lo-out-"))
    t0 = time.monotonic()
    try:
        try:
            proc = _run(soffice, docx, profile, outdir, timeout)
        except subprocess.TimeoutExpired:
            raise PdfConversionFailed(f"LibreOffice did not finish within {timeout:.0f} s", data={"docx_path": str(docx), "timeout": timeout})
        except OSError as e:
            raise PdfConversionFailed(f"could not start LibreOffice: {e}", data={"docx_path": str(docx)})
        produced = outdir / (docx.stem + ".pdf")
        if proc.returncode != 0 or not produced.exists() or produced.stat().st_size == 0:
            raise PdfConversionFailed(data={"docx_path": str(docx), "exit_code": proc.returncode,
                                            "stderr": proc.stderr[-2000:], "stdout": proc.stdout[-500:]})
        return produced, time.monotonic() - t0
    except PdfConversionFailed:
        shutil.rmtree(outdir, ignore_errors=True)       # never leave partial output behind
        raise


def convert_to_pdf(docx: Path, soffice: Path | None = None, timeout: float | None = None, profile_dir: Path | None = None) -> tuple[Path, float]:
    soffice = soffice or find_soffice()
    if soffice is None:
        raise LibreOfficeNotFound()
    persistent = profile_dir or _profile_dir
    with _LOCK:
        tmp_profile = None
        if persistent is None:
            tmp_profile = tempfile.TemporaryDirectory(prefix="docmaster-lo-")
            profile = Path(tmp_profile.name) / "profile"
        else:
            profile = persistent
        try:
            warm = (profile / WARM_MARKER).exists()
            limit = timeout or (CONVERT_TIMEOUT if warm else WARM_TIMEOUT)
            try:
                produced, seconds = _convert_once(soffice, docx, profile, limit)
            except PdfConversionFailed as first:
                if persistent is None:
                    raise
                # a damaged or half-written profile is the usual culprit: rebuild it and try once more
                log.warning("conversion failed (%s); rebuilding the LibreOffice profile and retrying", first)
                reset_profile(profile)
                try:
                    produced, seconds = _convert_once(soffice, docx, profile, WARM_TIMEOUT)
                except PdfConversionFailed as second:
                    second.data["first_attempt"] = str(first)
                    raise second
            if persistent is not None:
                profile.mkdir(parents=True, exist_ok=True)
                (profile / WARM_MARKER).write_text(soffice_version_cached(soffice), encoding="utf8")
            final = docx.with_suffix(".pdf")
            shutil.move(str(produced), final)
            shutil.rmtree(produced.parent, ignore_errors=True)
            return final, seconds
        finally:
            if tmp_profile is not None:
                tmp_profile.cleanup()


_version_cache: dict[str, str] = {}


def soffice_version_cached(soffice: Path) -> str:
    key = str(soffice)
    if key not in _version_cache:
        _version_cache[key] = soffice_version(soffice) or "unknown"
    return _version_cache[key]


def warm_profile(soffice: Path | None = None, profile_dir: Path | None = None) -> dict:
    """Convert a one-paragraph document so the profile's first-start work is done before the user needs it."""
    soffice = soffice or find_soffice()
    profile = profile_dir or _profile_dir
    if soffice is None or profile is None:
        return {"warmed": False, "reason": "no LibreOffice or no persistent profile"}
    if (profile / WARM_MARKER).exists() and (profile / WARM_MARKER).read_text(encoding="utf8") == soffice_version_cached(soffice):
        return {"warmed": True, "already": True}
    from docx import Document
    tmp = Path(tempfile.mkdtemp(prefix="docmaster-warm-"))
    try:
        d = Document(); d.add_paragraph("Papyra warm-up"); src = tmp / "warmup.docx"; d.save(src)
        t0 = time.monotonic()
        convert_to_pdf(src, soffice, profile_dir=profile)
        seconds = time.monotonic() - t0
        log.info("LibreOffice profile warmed in %.1f s", seconds)
        return {"warmed": True, "already": False, "seconds": round(seconds, 1)}
    except Exception as e:  # noqa: BLE001
        log.warning("LibreOffice warm-up failed: %s", e)
        return {"warmed": False, "reason": str(e)[:200]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def warm_profile_async(soffice: Path | None = None, profile_dir: Path | None = None) -> threading.Thread:
    t = threading.Thread(target=warm_profile, args=(soffice, profile_dir), name="lo-warmup", daemon=True)
    t.start()
    return t


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
