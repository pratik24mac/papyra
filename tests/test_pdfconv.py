"""Persistent LibreOffice profile: warm-up, reuse, marker, seeded settings, automatic rebuild on failure."""
import subprocess, sys
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from docmaster.pdfconv import libreoffice as lo  # noqa: E402
from docmaster.errors import PdfConversionFailed  # noqa: E402

DOCX = ROOT / "templates/resume-ats/v1/samples/example-output.docx"
HAS_LO = lo.find_soffice() is not None


@pytest.fixture(autouse=True)
def _isolate():
    lo.configure(None); lo._version_cache.clear()
    yield
    lo.configure(None)


@pytest.mark.skipif(not HAS_LO, reason="LibreOffice not installed")
def test_profile_is_created_seeded_warmed_and_reused(tmp_path):
    import shutil
    profile = tmp_path / "lo-profile"
    assert not lo.profile_is_warm(profile)
    r = lo.warm_profile(profile_dir=profile)
    assert r["warmed"] and not r["already"] and lo.profile_is_warm(profile)
    xcu = (profile / "user" / "registrymodifications.xcu").read_text()
    assert "AutoCheckEnabled" in xcu and "<value>false</value>" in xcu            # no update check, ever
    assert lo.warm_profile(profile_dir=profile) == {"warmed": True, "already": True}
    docx = tmp_path / "doc.docx"; shutil.copy(DOCX, docx)
    pdf, seconds = lo.convert_to_pdf(docx, profile_dir=profile)
    assert pdf.exists() and profile.exists() and lo.profile_is_warm(profile)       # profile survives conversions
    assert not list(Path(lo.tempfile.gettempdir()).glob("docmaster-lo-out-*"))     # no leftover output dirs


def test_failed_conversion_rebuilds_profile_and_retries(tmp_path, monkeypatch):
    profile = tmp_path / "lo-profile"; (profile / "user").mkdir(parents=True); (profile / lo.WARM_MARKER).write_text("x")
    (profile / "user" / "damaged").write_text("x")
    calls = []
    def fake_run(soffice, docx, prof, outdir, timeout):
        calls.append((prof.exists() and (prof / "user" / "damaged").exists(), timeout))
        if len(calls) == 1:
            return subprocess.CompletedProcess([], 1, "", "crash")
        (outdir / (docx.stem + ".pdf")).write_bytes(b"%PDF-1.4 fake")
        return subprocess.CompletedProcess([], 0, "", "")
    monkeypatch.setattr(lo, "_run", fake_run)
    monkeypatch.setattr(lo, "soffice_version_cached", lambda s: "v")
    docx = tmp_path / "d.docx"; docx.write_bytes(b"x")
    pdf, _ = lo.convert_to_pdf(docx, soffice=Path(sys.executable), profile_dir=profile)
    assert pdf.read_bytes().startswith(b"%PDF")
    assert calls[0] == (True, lo.CONVERT_TIMEOUT)          # warm profile → short timeout
    assert calls[1] == (False, lo.WARM_TIMEOUT)            # rebuilt (damage gone) → generous timeout
    assert lo.profile_is_warm(profile)


def test_two_failures_report_both(tmp_path, monkeypatch):
    profile = tmp_path / "p"
    monkeypatch.setattr(lo, "_run", lambda *a, **k: subprocess.CompletedProcess([], 77, "", "boom"))
    docx = tmp_path / "d.docx"; docx.write_bytes(b"x")
    with pytest.raises(PdfConversionFailed) as e:
        lo.convert_to_pdf(docx, soffice=Path(sys.executable), profile_dir=profile)
    assert e.value.data["exit_code"] == 77 and "first_attempt" in e.value.data


def test_timeout_message_names_the_limit(tmp_path, monkeypatch):
    def slow(*a, **k): raise subprocess.TimeoutExpired("soffice", k.get("timeout", a[-1]))
    monkeypatch.setattr(lo, "_run", slow)
    docx = tmp_path / "d.docx"; docx.write_bytes(b"x")
    with pytest.raises(PdfConversionFailed) as e:
        lo.convert_to_pdf(docx, soffice=Path(sys.executable), profile_dir=tmp_path / "p")
    assert f"{lo.WARM_TIMEOUT:.0f} s" in str(e.value) and e.value.data["timeout"] == lo.WARM_TIMEOUT
