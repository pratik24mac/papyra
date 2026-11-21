"""Engine self-check: which runtime modules are present, whether LibreOffice is usable, and a real
test conversion with timings. Run at startup (modules only) and on demand from Settings →
Diagnostics (full), so a broken build or a broken machine explains itself instead of crashing
in the middle of a document."""
from __future__ import annotations
import importlib, platform, sys, tempfile, time, shutil
from pathlib import Path

RUNTIME_MODULES = ("docx", "docxtpl", "lxml", "pypdf", "yaml", "keyring", "psutil", "jinja2", "PIL")


def check_modules() -> list[dict]:
    out = []
    for name in RUNTIME_MODULES:
        try:
            mod = importlib.import_module(name)
            out.append({"check": f"module {name}", "ok": True, "detail": getattr(mod, "__version__", "") or "present"})
        except Exception as e:  # noqa: BLE001
            out.append({"check": f"module {name}", "ok": False, "detail": f"{type(e).__name__}: {e}", "fix": "The engine was packaged without this dependency. Rebuild it after `pip install -r tools/requirements.txt` (tools/build_backend.py now refuses to build without it)."})
    return out


def missing_modules() -> list[str]:
    return [c["check"].split()[1] for c in check_modules() if not c["ok"]]


def run(soffice_override: str | None, data_dir: Path | None, convert: bool = True) -> dict:
    from .pdfconv import libreoffice as lo
    checks = check_modules()
    checks.append({"check": "python", "ok": True, "detail": f"{platform.python_version()} frozen={bool(getattr(sys, 'frozen', False))} {platform.platform()}"})
    soffice = lo.find_soffice(soffice_override)
    if soffice is None:
        checks.append({"check": "LibreOffice installed", "ok": False, "detail": "soffice not found in the standard locations", "fix": "Install LibreOffice to its default folder, or set DOCMASTER_SOFFICE."})
    else:
        checks.append({"check": "LibreOffice installed", "ok": True, "detail": f"{soffice} · {lo.soffice_version_cached(soffice)}"})
        profile = lo._profile_dir
        checks.append({"check": "LibreOffice profile", "ok": True, "detail": f"{profile} · {'warm' if lo.profile_is_warm() else 'cold (first conversion will be slow)'}"})
        leftovers = lo._profile_processes(profile) if profile and not missing_modules() else []
        checks.append({"check": "No leftover LibreOffice processes", "ok": not leftovers, "detail": f"{len(leftovers)} running with the Papyra profile" + (" (will be killed before the next conversion)" if leftovers else "")})
        if convert and not missing_modules():
            from docx import Document
            tmp = Path(tempfile.mkdtemp(prefix="docmaster-check-"))
            try:
                d = Document(); d.add_paragraph("Papyra diagnostics " + time.strftime("%Y-%m-%d %H:%M:%S")); src = tmp / "check.docx"; d.save(src)
                t0 = time.monotonic()
                pdf, seconds = lo.convert_to_pdf(src, soffice)
                pages = lo.validate_pdf(pdf, {"min": 1, "max": 1}, ["Papyra diagnostics"])
                checks.append({"check": "Test PDF conversion", "ok": True, "detail": f"{seconds:.1f} s, {pages} page, total {time.monotonic() - t0:.1f} s"})
            except Exception as e:  # noqa: BLE001
                data = getattr(e, "data", {}) or {}
                detail = f"{type(e).__name__}: {e}"
                if data.get("stderr"): detail += f" · stderr: {str(data['stderr'])[-300:]}"
                checks.append({"check": "Test PDF conversion", "ok": False, "detail": detail, "fix": "See the log below. On Windows: end all LibreOffice processes in Task Manager and run the check again; if it keeps failing, add a Windows Defender exclusion for the LibreOffice folder."})
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
    log_lines: list[str] = []
    log_path = data_dir / "logs" / "backend.log" if data_dir else None
    if log_path and log_path.exists():
        try:
            log_lines = log_path.read_text(encoding="utf8", errors="replace").splitlines()[-40:]
        except OSError:
            pass
    return {"ok": all(c["ok"] for c in checks), "checks": checks, "log_path": str(log_path) if log_path else None, "log_tail": log_lines}
