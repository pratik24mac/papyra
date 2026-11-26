"""Job records / staleness, template linter and OOXML helpers."""
import json, shutil, subprocess, sys, zipfile
from pathlib import Path
import pytest, yaml
from docx import Document
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from docmaster.storage.jobs import JobRecord, JobStore, JobNotFound, sha256_of  # noqa: E402
from docmaster.docgen.linter import lint_template, lint_catalogue  # noqa: E402
from docmaster.docgen import ooxml  # noqa: E402

TPL = ROOT / "templates" / "resume-ats" / "v1"


def test_job_record_detects_external_docx_edit(tmp_path):
    docx = tmp_path / "a.docx"; shutil.copy(TPL / "samples" / "example-output.docx", docx)
    pdf = tmp_path / "a.pdf"; shutil.copy(TPL / "samples" / "example-output.pdf", pdf)
    store = JobStore(tmp_path / "jobs")
    rec = JobRecord.new("job-1", "resume-ats", 1, docx, {"min": 1, "max": 3})
    rec.set_pdf(pdf, 2); store.save(rec)
    rec = store.load("job-1")
    assert rec.current_state() == {"docx_exists": True, "docx_changed": False, "pdf_exists": True, "pdf_changed": False, "pdf_stale": False}
    d = Document(docx); d.paragraphs[0].runs[0].text = "EDITED"; d.save(docx)      # user edits the Word file
    st = rec.current_state()
    assert st["docx_changed"] and st["pdf_stale"]
    pdf.unlink()
    assert rec.current_state()["pdf_stale"] and not rec.current_state()["pdf_exists"]


def test_job_ids_are_validated(tmp_path):
    store = JobStore(tmp_path)
    for bad in ("../x", "a/b", "", "x" * 65, "-lead"):
        with pytest.raises(JobNotFound):
            store.load(bad)
    with pytest.raises(JobNotFound):
        store.load("missing-job")


def test_bundled_templates_pass_lint():
    results = lint_catalogue(ROOT / "templates")
    assert results, "no templates found"
    for name, findings in results.items():
        assert not [f for f in findings if f.level == "error"], f"{name}: {[str(f) for f in findings]}"


def test_linter_catches_authoring_mistakes(tmp_path):
    schema = yaml.safe_load((TPL / "schema.yaml").read_text())
    # 1) schema field never used + unknown variable in template
    bad_schema = json.loads(json.dumps(schema)); bad_schema["groups"][0]["fields"].append({"id": "extra", "label": "Extra", "type": "text"})
    codes = {f.code for f in lint_template(TPL / "template.docx", bad_schema)}
    assert "M002" in codes
    # 2) text after a {{r }} tag, smart quote, unbalanced tag
    d = Document(TPL / "template.docx")
    p = d.add_paragraph(); r = p.add_run("{{r github_link }} trailing"); d.add_paragraph("“{{ full_name }}”"); d.add_paragraph("{{ oops")
    out = tmp_path / "bad.docx"; d.save(out)
    codes = {f.code for f in lint_template(out, schema)}
    assert {"T003", "L001", "T001"} <= codes
    # 3) reserved id
    bad_schema = json.loads(json.dumps(schema)); bad_schema["groups"][2]["fields"][0]["item_fields"][1]["id"] = "items"
    assert "S002" in {f.code for f in lint_template(TPL / "template.docx", bad_schema)}


def test_lint_cli_passes():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "lint_templates.py"), str(ROOT / "templates")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_ooxml_restart_numbering_and_fields(tmp_path):
    d = Document(TPL / "samples" / "example-output.docx")
    numbered = [p for p in d.paragraphs if p._p.find(f"{qn('w:pPr')}/{qn('w:numPr')}") is not None]
    before = ooxml.defined_num_ids(d)
    new_id = ooxml.restart_numbering(d, numbered[5], start=1)
    assert str(new_id) in ooxml.defined_num_ids(d) and str(new_id) not in before
    assert numbered[5]._p.find(f"{qn('w:pPr')}/{qn('w:numPr')}/{qn('w:numId')}").get(qn("w:val")) == str(new_id)
    num = [n for n in d.part.numbering_part.element.findall(qn("w:num")) if n.get(qn("w:numId")) == str(new_id)][0]
    assert num.find(f"{qn('w:lvlOverride')}/{qn('w:startOverride')}").get(qn("w:val")) == "1"
    p = d.add_paragraph("Page "); ooxml.insert_field(p, "PAGE"); p.add_run(" of "); ooxml.insert_field(p, "NUMPAGES")
    ooxml.mark_fields_dirty(d); ooxml.set_document_properties(d, "Title X", subject="S")
    out = tmp_path / "o.docx"; d.save(out)
    xml = zipfile.ZipFile(out).read("word/document.xml").decode()
    assert " PAGE " in xml and " NUMPAGES " in xml and xml.count('w:fldCharType="begin"') == 2
    assert 'w:updateFields' in zipfile.ZipFile(out).read("word/settings.xml").decode()
    d2 = Document(out); assert d2.core_properties.title == "Title X" and d2.core_properties.subject == "S"
    assert ooxml.numbering_ids_in_use(d2) <= ooxml.defined_num_ids(d2)
    assert not ooxml.has_tracked_changes(d2) and not ooxml.has_comments(d2)


def test_sha256_matches_hashlib(tmp_path):
    import hashlib
    f = tmp_path / "x"; f.write_bytes(b"abc" * 1000)
    assert sha256_of(f) == hashlib.sha256(b"abc" * 1000).hexdigest()


def test_cross_template_type_clash_is_a_warning():
    from docmaster.docgen.linter import cross_template_findings
    a = {"groups": [{"id": "g", "label": "G", "fields": [{"id": "headline", "label": "H", "type": "text"}, {"id": "full_name", "label": "N", "type": "text"}]}]}
    b = {"groups": [{"id": "g", "label": "G", "fields": [{"id": "headline", "label": "Tone", "type": "select", "options": ["x"]}, {"id": "full_name", "label": "N", "type": "text"}]}]}
    f = cross_template_findings({"resume v1": a, "cover v1": b})
    assert len(f) == 1 and f[0].code == "M004" and f[0].level == "warning" and "headline" in f[0].message and "full_name" not in f[0].message
    assert cross_template_findings({"resume v1": a}) == []


def test_template_without_any_list_lints_fine(tmp_path):
    """A plain document has no numbering part; python-docx throws when asked to create one, which
    surfaced as 'template cannot be opened' for every list-free user template (2026-11-26)."""
    from docx import Document
    from docmaster.docgen.ooxml import defined_num_ids, numbering_ids_in_use
    d = Document(); d.add_paragraph("Hello {{ name }}")
    for rid, rel in list(d.part.rels.items()):                 # python-docx's default document ships a numbering part: drop it
        if rel.reltype.endswith("/numbering"):
            d.part.drop_rel(rid)
    src = tmp_path / "plain.docx"; d.save(src)
    import zipfile
    assert not any(n.endswith("numbering.xml") for n in zipfile.ZipFile(src).namelist())
    assert defined_num_ids(Document(src)) == set() and numbering_ids_in_use(Document(src)) == set()
    schema = {"template": {"id": "plain", "version": 1, "name": "Plain", "file": "plain.docx"}, "groups": [{"id": "g", "label": "G", "fields": [{"id": "name", "label": "N", "type": "text", "required": True}]}]}
    assert [str(f) for f in lint_template(src, schema) if f.level == "error"] == []
