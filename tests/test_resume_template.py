"""Template tests for templates/resume-ats/v1. PDF test is skipped when LibreOffice is absent."""
import copy, shutil, subprocess, sys, zipfile
from pathlib import Path
import pytest, yaml
from docx import Document
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "backend"))
from render_template import render, ValidationError, RESERVED_IDS  # noqa: E402

TPL = ROOT / "templates" / "resume-ats" / "v1"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
from docmaster.pdfconv.libreoffice import find_soffice  # noqa: E402
SOFFICE = str(find_soffice()) if find_soffice() else None


@pytest.fixture
def values():
    return yaml.safe_load((TPL / "values.example.yaml").read_text())


def write(tmp_path, data):
    p = tmp_path / "values.yaml"; p.write_text(yaml.safe_dump(data, allow_unicode=True)); return p


def numbered_paragraphs(path):
    body = etree.fromstring(zipfile.ZipFile(path).read("word/document.xml")).find(W + "body")
    return [p for p in body.iter(W + "p") if p.find(f"{W}pPr/{W}numPr") is not None]


def test_example_renders_full_document(tmp_path, values):
    out = render(TPL, write(tmp_path, values), tmp_path / "out.docx")
    texts = [p.text for p in Document(out).paragraphs]
    assert texts[0] == "ASHA VERMA"
    assert "{{" not in "".join(texts) and "{%" not in "".join(texts)
    assert len(numbered_paragraphs(out)) == 19 + 3            # experience bullets + achievements
    assert "Frontend Architect — Northwind Digital\tAug 2024 – Present" in texts
    assert "Other: Jira, Stripe Payment Gateway" in texts
    for heading in ("ACHIEVEMENTS", "DOMAIN EXPERTISE", "LANGUAGES"):
        assert heading in texts
    with zipfile.ZipFile(out) as z:
        rels = z.read("word/_rels/document.xml.rels").decode()
    assert "github.com/asha-verma-example" in rels and "linkedin.com" in rels   # hyperlinks created as relationships


def test_optional_sections_are_omitted(tmp_path, values):
    v = copy.deepcopy(values)
    for k in ("achievements", "domain_expertise", "languages", "skills_other", "github_url", "linkedin_url"):
        v.pop(k)
    out = render(TPL, write(tmp_path, v), tmp_path / "out.docx")
    texts = [p.text for p in Document(out).paragraphs]
    for heading in ("ACHIEVEMENTS", "DOMAIN EXPERTISE", "LANGUAGES"):
        assert heading not in texts
    assert not any(t.startswith("Other:") for t in texts)
    assert texts[2] == "asha.verma@example.com  |  +91 98765 43210"      # no dangling separators
    assert len(numbered_paragraphs(out)) == 19


def test_missing_required_value_is_rejected(tmp_path, values):
    v = copy.deepcopy(values); v["full_name"] = ""
    v["experience"][0]["bullets"] = []
    with pytest.raises(ValidationError) as e:
        render(TPL, write(tmp_path, v), tmp_path / "out.docx")
    errs = " ".join(e.value.data["errors"])
    assert "full_name: required" in errs and "experience[0].bullets" in errs


def test_xml_special_characters_are_escaped(tmp_path, values):
    v = copy.deepcopy(values); v["headline"] = "R&D <Lead> \"Platforms\""
    out = render(TPL, write(tmp_path, v), tmp_path / "out.docx")
    assert Document(out).paragraphs[1].text == 'R&D <Lead> "Platforms"'


def test_reserved_ids_cover_dict_methods():
    assert {"items", "keys", "values", "get", "loop"} <= RESERVED_IDS


@pytest.mark.skipif(SOFFICE is None, reason="LibreOffice not installed")
def test_pdf_pages_and_text(tmp_path, values):
    from pypdf import PdfReader
    out = render(TPL, write(tmp_path, values), tmp_path / "out.docx")
    subprocess.run([SOFFICE, "--headless", "--norestore", f"-env:UserInstallation=file://{tmp_path}/lo", "--convert-to", "pdf",
                    "--outdir", str(tmp_path), str(out)], check=True, capture_output=True, timeout=120)
    pdf = PdfReader(tmp_path / "out.pdf")
    assert len(pdf.pages) == 2
    text = "\n".join(p.extract_text() for p in pdf.pages)
    assert "ASHA VERMA" in text and "asha.verma@example.com" in text
    assert "Frontend Architect — Northwind Digital Aug 2024" in text          # tab renders as separation


@pytest.mark.skipif(SOFFICE is None or shutil.which("pdftoppm") is None, reason="LibreOffice/poppler not installed")
def test_matches_approved_reference(tmp_path, values):
    """Regression gate: page count, text and pixels against the approved reference.pdf (synthetic fixture, approved 2026-11-06)."""
    from pypdf import PdfReader
    from PIL import Image, ImageChops
    out = render(TPL, write(tmp_path, values), tmp_path / "out.docx")
    subprocess.run([SOFFICE, "--headless", "--norestore", f"-env:UserInstallation=file://{tmp_path}/lo", "--convert-to", "pdf",
                    "--outdir", str(tmp_path), str(out)], check=True, capture_output=True, timeout=120)
    ref, new = PdfReader(TPL / "reference.pdf"), PdfReader(tmp_path / "out.pdf")
    assert len(new.pages) == len(ref.pages)
    for a, b in zip(ref.pages, new.pages):
        assert a.extract_text().splitlines() == b.extract_text().splitlines()
    subprocess.run(["pdftoppm", "-r", "72", "-png", str(TPL / "reference.pdf"), str(tmp_path / "ref")], check=True)
    subprocess.run(["pdftoppm", "-r", "72", "-png", str(tmp_path / "out.pdf"), str(tmp_path / "new")], check=True)
    for i in range(1, len(ref.pages) + 1):
        ia, ib = Image.open(tmp_path / f"ref-{i}.png").convert("L"), Image.open(tmp_path / f"new-{i}.png").convert("L")
        px = list(ImageChops.difference(ia, ib).getdata())
        assert sum(1 for v in px if v > 40) / len(px) < 0.005, f"page {i} differs from reference by more than 0.5 %"
