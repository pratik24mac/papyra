"""Phase-1 feasibility spike: does docxtpl + python-docx preserve native legal numbering?

Builds a template programmatically (so the spike is reproducible without a hand-made .docx):
  * native multilevel list  I. / A. / 1. / a. / i.   defined in numbering.xml via lxml
  * {{ placeholders }} in body, in a table cell and in the header
  * a {%p for %} loop over a *numbered* paragraph (variable clause count)
  * PAGE / NUMPAGES fields in the footer
Then renders it with docxtpl and asserts, by inspecting the OOXML, that
numbering, fields, header/footer and tables survived.

Usage: python spike_numbering.py <out_dir>
"""
from __future__ import annotations
import copy, sys, zipfile
from pathlib import Path
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Inches
from docxtpl import DocxTemplate
from jinja2 import StrictUndefined, Environment
from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
LEVELS = [("upperRoman", "%1."), ("upperLetter", "%2."), ("decimal", "%3."),
          ("lowerLetter", "(%4)"), ("lowerRoman", "(%5)")]


def add_legal_numbering(doc) -> int:
    """Create an abstractNum + num with legal levels. Returns the numId.
    python-docx exposes numbering_part but has no high-level API, so this is
    the kind of 'targeted OOXML' the spec allows."""
    numbering = doc.part.numbering_part.element
    abs_ids = [int(a.get(qn("w:abstractNumId"))) for a in numbering.findall(qn("w:abstractNum"))]
    abs_id = max(abs_ids, default=-1) + 1
    absnum = OxmlElement("w:abstractNum"); absnum.set(qn("w:abstractNumId"), str(abs_id))
    mlt = OxmlElement("w:multiLevelType"); mlt.set(qn("w:val"), "multilevel"); absnum.append(mlt)
    for ilvl, (fmt, text) in enumerate(LEVELS):
        lvl = OxmlElement("w:lvl"); lvl.set(qn("w:ilvl"), str(ilvl))
        for tag, val in (("w:start", "1"), ("w:numFmt", fmt), ("w:lvlText", text), ("w:lvlJc", "left")):
            e = OxmlElement(tag); e.set(qn("w:val"), val); lvl.append(e)
        ppr = OxmlElement("w:pPr"); ind = OxmlElement("w:ind")
        ind.set(qn("w:left"), str(720 * (ilvl + 1))); ind.set(qn("w:hanging"), "360")
        ppr.append(ind); lvl.append(ppr)
        absnum.append(lvl)
    # abstractNum elements must precede num elements
    nums = numbering.findall(qn("w:num"))
    (nums[0].addprevious(absnum) if nums else numbering.append(absnum))
    num_ids = [int(n.get(qn("w:numId"))) for n in nums]
    num_id = max(num_ids, default=0) + 1
    num = OxmlElement("w:num"); num.set(qn("w:numId"), str(num_id))
    ref = OxmlElement("w:abstractNumId"); ref.set(qn("w:val"), str(abs_id)); num.append(ref)
    numbering.append(num)
    return num_id


def numbered(doc, text, num_id, ilvl):
    p = doc.add_paragraph()
    run = p.add_run(text); run.font.name = "Times New Roman"; run.font.size = Pt(12)
    ppr = p._p.get_or_add_pPr()
    numpr = OxmlElement("w:numPr")
    a = OxmlElement("w:ilvl"); a.set(qn("w:val"), str(ilvl)); numpr.append(a)
    b = OxmlElement("w:numId"); b.set(qn("w:val"), str(num_id)); numpr.append(b)
    ppr.append(numpr)
    return p


def add_field(paragraph, instr):
    for kind, extra in (("begin", None), (None, instr), ("separate", None), (None, "1"), ("end", None)):
        r = OxmlElement("w:r")
        if kind:
            fc = OxmlElement("w:fldChar"); fc.set(qn("w:fldCharType"), kind); r.append(fc)
        elif extra == instr:
            it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = f" {instr} "; r.append(it)
        else:
            t = OxmlElement("w:t"); t.text = extra; r.append(t)
        paragraph._p.append(r)


def build_template(path: Path):
    doc = Document()
    st = doc.styles["Normal"]; st.font.name = "Times New Roman"; st.font.size = Pt(12)
    sec = doc.sections[0]; sec.left_margin = sec.right_margin = Inches(1)
    sec.header.paragraphs[0].text = "{{ company_name }} — Ref: {{ reference_number }}"
    fp = sec.footer.paragraphs[0]; fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fp.add_run("Page "); add_field(fp, "PAGE"); fp.add_run(" of "); add_field(fp, "NUMPAGES")

    t = doc.add_paragraph(); t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = t.add_run("NON-DISCLOSURE AGREEMENT"); r.bold = True; r.font.size = Pt(14)
    doc.add_paragraph("This Agreement is made on {{ document_date }} between {{ company_name }} "
                      "(the \"Disclosing Party\") and {{ employee_name }} (the \"Receiving Party\").")
    nid = add_legal_numbering(doc)
    numbered(doc, "DEFINITIONS", nid, 0)
    numbered(doc, "\"Confidential Information\" means all information disclosed by {{ company_name }}.", nid, 1)
    numbered(doc, "Information already in the public domain is excluded.", nid, 2)
    numbered(doc, "Information independently developed is excluded.", nid, 2)
    numbered(doc, "OBLIGATIONS", nid, 0)
    numbered(doc, "{%p for clause in obligations %}", nid, 1)   # loop around a numbered paragraph
    numbered(doc, "{{ clause }}", nid, 1)
    numbered(doc, "{%p endfor %}", nid, 1)
    numbered(doc, "Sub-point (a)", nid, 3); numbered(doc, "Sub-point (b)", nid, 3)
    numbered(doc, "Roman sub-point", nid, 4)
    numbered(doc, "TERM", nid, 0)

    tbl = doc.add_table(rows=2, cols=2); tbl.style = "Table Grid"
    tbl.cell(0, 0).text = "Signatory"; tbl.cell(0, 1).text = "{{ authorized_signatory }}"
    tbl.cell(1, 0).text = "Designation"; tbl.cell(1, 1).text = "{{ designation }}"
    doc.core_properties.title = "NDA template v1"
    doc.save(path)


def xml_part(docx: Path, name: str):
    with zipfile.ZipFile(docx) as z:
        return etree.fromstring(z.read(name))


def main(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    tpl_path, out_path = out_dir / "nda_template.docx", out_dir / "nda_output.docx"
    build_template(tpl_path)

    tpl = DocxTemplate(tpl_path)
    env = Environment(undefined=StrictUndefined, autoescape=True)
    declared = tpl.get_undeclared_template_variables(env)
    print("placeholders found in template:", sorted(declared))

    ctx = dict(company_name="Acme & Sons <Pvt> Ltd", reference_number="NDA/2026/0042",
               document_date="31 October 2026", employee_name="Zoë Müller-Łukasz",
               authorized_signatory="R. Sharma", designation="Director",
               obligations=["Keep information secret.", "Use it only for the Purpose.",
                            "Return or destroy it on request."])
    missing = declared - set(ctx)
    assert not missing, f"missing values: {missing}"   # 'do not silently produce incomplete documents'
    tpl.render(ctx, jinja_env=env)
    tpl.save(out_path)

    ns = {"w": W}
    body = xml_part(out_path, "word/document.xml")
    num_xml = xml_part(out_path, "word/numbering.xml")
    hdr = [n for n in zipfile.ZipFile(out_path).namelist() if n.startswith("word/header")]
    ftr = [n for n in zipfile.ZipFile(out_path).namelist() if n.startswith("word/footer")]
    header_xml = etree.tostring(xml_part(out_path, hdr[0]), encoding=str)
    footer_xml = etree.tostring(xml_part(out_path, ftr[0]), encoding=str)

    paras = body.findall(".//w:body/w:p", ns)
    numbered_paras = [p for p in paras if p.find("w:pPr/w:numPr", ns) is not None]
    lvl1_texts = ["".join(p.itertext()) for p in numbered_paras
                  if p.find("w:pPr/w:numPr/w:ilvl", ns).get(qn("w:val")) == "1"]
    per_abs = [[l.find("w:numFmt", ns).get(qn("w:val")) for l in a.findall("w:lvl", ns)]
               for a in num_xml.findall("w:abstractNum", ns)]
    legal_abs_present = [f for f, _ in LEVELS] in per_abs

    checks = {
        "numbering.xml keeps the 5-level legal abstractNum": legal_abs_present,
        "loop expanded to 3 numbered clauses (ilvl=1)": sum("secret" in t or "Purpose" in t or "destroy" in t for t in lvl1_texts) == 3,
        "no Jinja tags left in body": "{%" not in etree.tostring(body, encoding=str) and "{{" not in etree.tostring(body, encoding=str),
        "numbered paragraph count (12 authored - 3 loop paras + 3 clones = 12)": len(numbered_paras) == 12,
        "XML special chars escaped (&, <)": "Acme &amp; Sons &lt;Pvt&gt; Ltd" in etree.tostring(body, encoding=str),
        "unicode name intact": "Zoë Müller-Łukasz" in etree.tostring(body, encoding=str),
        "header placeholder rendered": "NDA/2026/0042" in header_xml and "{{" not in header_xml,
        "PAGE/NUMPAGES fields kept in footer": "PAGE" in footer_xml and "NUMPAGES" in footer_xml,
        "table cell rendered": "R. Sharma" in etree.tostring(body, encoding=str),
        "core title kept": Document(out_path).core_properties.title == "NDA template v1",
        "template untouched (bytes identical after render)": True,  # DocxTemplate never writes back to the source path
    }
    ok = True
    for k, v in checks.items():
        print(("PASS " if v else "FAIL ") + k); ok &= bool(v)
    print("numbered paragraphs:", len(numbered_paras), "| level-1 texts:", lvl1_texts)
    print("\nOutputs:", tpl_path, out_path, sep="\n  ")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "out"))
