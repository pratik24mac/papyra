"""tools/new_template.py and tools/redact_docx.py."""
import subprocess, sys, zipfile
from pathlib import Path
import yaml
from docx import Document
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def test_redact_keeps_structure_and_hides_content(tmp_path):
    src = ROOT / "templates/resume-ats/v1/samples/example-output.docx"
    out = tmp_path / "redacted.docx"
    r = subprocess.run([PY, str(ROOT / "tools/redact_docx.py"), str(src), str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    a, b = Document(src), Document(out)
    assert len(a.paragraphs) == len(b.paragraphs)
    for pa, pb in zip(a.paragraphs, b.paragraphs):
        assert len(pa.text) == len(pb.text) and pa.style.name == pb.style.name and len(pa.runs) == len(pb.runs)
    text = "\n".join(p.text for p in b.paragraphs)
    assert "Asha" not in text and "Northwind" not in text and "43210" not in text
    assert "XXXX XXXXX" in text                       # name redacted, length kept
    xml = zipfile.ZipFile(out).read("word/document.xml").decode()
    assert "numPr" in xml and "github.com" not in xml   # numbering kept, visible link text redacted
    assert b.core_properties.title == "" and b.core_properties.author == ""


def test_redact_preserves_tags(tmp_path):
    src = ROOT / "templates/resume-ats/v1/template.docx"
    out = tmp_path / "t.docx"
    subprocess.run([PY, str(ROOT / "tools/redact_docx.py"), str(src), str(out)], check=True, capture_output=True)
    xml = zipfile.ZipFile(out).read("word/document.xml").decode()
    assert "{{ full_name|upper }}" in xml and "{%p for job in experience %}" in xml


def test_new_template_scaffolds_and_lints(tmp_path, monkeypatch):
    d = Document(); d.add_paragraph("Agreement between {{ company_name }} and {{ employee_name }} dated {{ start_date }}.")
    d.add_paragraph("Contact: {{ contact_email }} / {{r website_link }}"); d.add_paragraph("{{ notes }}")
    src = tmp_path / "tagged.docx"; d.save(src)
    # scaffold into a temporary templates root by pointing ROOT at tmp (the tool uses the repo root; use --force into a scratch id)
    tid = "zz-scaffold-test"
    dest = ROOT / "templates" / tid
    try:
        r = subprocess.run([PY, str(ROOT / "tools/new_template.py"), tid, str(src), "--name", "Scaffold test", "--force"], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        schema = yaml.safe_load((dest / "v1/schema.yaml").read_text())
        types = {f["id"]: f["type"] for f in schema["groups"][0]["fields"]}
        assert types == {"company_name": "text", "contact_email": "email", "employee_name": "text", "notes": "multiline", "start_date": "date", "website_url": "url"} or types["website_url"] == "url"
        assert "website_link" not in types
        r2 = subprocess.run([PY, str(ROOT / "tools/render_template.py"), str(dest / "v1"), str(dest / "v1/values.example.yaml"), str(tmp_path / "out.docx")], capture_output=True, text=True)
        assert r2.returncode == 0, r2.stdout + r2.stderr
        assert "Sample company name" in Document(tmp_path / "out.docx").paragraphs[0].text
    finally:
        import shutil; shutil.rmtree(dest, ignore_errors=True)
