"""Date formatting, full-quality PDF images, and the trailing blank page."""
import shutil, sys
from pathlib import Path
import pytest, yaml
from docx import Document
from docx.shared import Inches
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from docmaster.docgen.dates import format_date, check_format, date_filter, FormattedDate  # noqa: E402
from docmaster.docgen.render import render_docx  # noqa: E402
from docmaster.docgen.ooxml import trim_trailing_blank  # noqa: E402
from docmaster.pdfconv.libreoffice import convert_to_pdf, find_soffice  # noqa: E402
from docmaster.storage.settings import Settings, SettingInvalid  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402

HAS_LO = find_soffice() is not None


def test_date_tokens_and_strftime():
    assert format_date("2026-03-05", "D MMMM YYYY") == "5 March 2026"
    assert format_date("2026-03-05", "DD/MM/YYYY") == "05/03/2026"
    assert format_date("2026-03-22", "Do MMMM YYYY") == "22nd March 2026"
    assert format_date("2026-03-11", "Do MMM YY") == "11th Mar 26"
    assert format_date("2026-03-05", "MMMM D, YYYY") == "March 5, 2026"
    assert format_date("2026-03-05", "%d %b %Y") == "05 Mar 2026" and format_date("2026-03-05", "%-d %B %Y") == "5 March 2026"
    assert check_format("DD-MMM-YYYY") == "12-Mar-2026"
    with pytest.raises(ValueError): check_format("hello")
    assert date_filter(FormattedDate("5 March 2026", "2026-03-05"), "YYYY-MM-DD") == "2026-03-05"
    assert date_filter("2026-03-05", "DD/MM/YYYY") == "05/03/2026" and date_filter("not a date") == "not a date"


def schema_with_dates():
    return {"template": {"id": "t", "version": 1, "name": "T", "file": "t.docx", "date_format": "DD/MM/YYYY"},
            "groups": [{"id": "g", "label": "G", "fields": [
                {"id": "start", "label": "Start", "type": "date", "required": True},
                {"id": "signed", "label": "Signed", "type": "date", "required": True, "format": "Do MMMM YYYY"},
                {"id": "events", "label": "Events", "type": "group_list", "required": False,
                 "item_fields": [{"id": "when", "label": "When", "type": "date", "required": True}, {"id": "what", "label": "What", "type": "text", "required": True}]}]}]}


def test_dates_render_with_field_template_and_setting_precedence(tmp_path):
    d = Document(); d.add_paragraph("Start {{ start }} / signed {{ signed }} / iso {{ start | date(\"YYYY-MM-DD\") }}")
    d.add_paragraph("{%p for e in events %}"); d.add_paragraph("{{ e.when }}: {{ e.what }}"); d.add_paragraph("{%p endfor %}")
    src = tmp_path / "t.docx"; d.save(src)
    values = {"start": "2026-03-05", "signed": "2026-03-22", "events": [{"when": "2026-01-02", "what": "kick-off"}]}
    out = render_docx(src, schema_with_dates(), values, tmp_path / "o.docx", default_date_format="MMMM D, YYYY")
    text = "\n".join(p.text for p in Document(out).paragraphs)
    assert "Start 05/03/2026" in text               # template date_format beats the app setting
    assert "signed 22nd March 2026" in text         # field format beats the template
    assert "iso 2026-03-05" in text                 # in-template filter re-formats from the ISO value
    assert "02/01/2026: kick-off" in text           # dates inside repeating groups too
    schema = schema_with_dates(); del schema["template"]["date_format"]
    out = render_docx(src, schema, values, tmp_path / "o2.docx", default_date_format="MMMM D, YYYY")
    assert "Start March 5, 2026" in Document(out).paragraphs[0].text   # app setting applies when the template has none


def test_date_format_setting_is_validated(tmp_path):
    s = Settings(tmp_path / "d", tmp_path / "o")
    assert s.all()["date_format"] == "D MMMM YYYY"
    s.set("date_format", "DD-MMM-YYYY"); assert s.all()["date_format"] == "DD-MMM-YYYY"
    with pytest.raises(SettingInvalid): s.set("date_format", "no tokens here")


def body_tags(doc):
    return [c.tag.split("}")[1] for c in doc.element.body if not c.tag.endswith("sectPr")]


def test_trailing_blank_paragraphs_and_page_break_are_removed(tmp_path):
    d = Document(); d.add_paragraph("Last real line"); d.add_paragraph(""); p = d.add_paragraph(""); p.add_run().add_break(__import__("docx").enum.text.WD_BREAK.PAGE); d.add_paragraph("")
    assert trim_trailing_blank(d) == 3
    assert [p.text for p in d.paragraphs] == ["Last real line"]
    assert trim_trailing_blank(d) == 0                                  # idempotent


def test_paragraph_after_final_table_is_kept_but_shrunk(tmp_path):
    d = Document(); d.add_paragraph("Intro"); t = d.add_table(rows=1, cols=1); t.cell(0, 0).text = "x"; d.add_paragraph("")
    assert body_tags(d) == ["p", "tbl", "p"]
    assert trim_trailing_blank(d) == 1                                  # the paragraph after the table is kept, shrunk
    assert body_tags(d) == ["p", "tbl", "p"]
    last = d.element.body.findall(qn("w:p"))[-1]
    assert last.find(f"{qn('w:pPr')}/{qn('w:rPr')}/{qn('w:sz')}").get(qn("w:val")) == "2"
    assert last.find(f"{qn('w:pPr')}/{qn('w:spacing')}").get(qn("w:line")) == "20"
    d2 = Document(); d2.add_table(rows=1, cols=1).cell(0, 0).text = "x"
    assert body_tags(d2) == ["tbl"] and trim_trailing_blank(d2) == 1 and body_tags(d2) == ["tbl", "p"]


def test_render_trims_unless_template_opts_out(tmp_path):
    d = Document(); d.add_paragraph("Hello {{ name }}"); d.add_paragraph(""); d.add_paragraph("")
    src = tmp_path / "t.docx"; d.save(src)
    schema = {"template": {"id": "t", "version": 1, "name": "T", "file": "t.docx"}, "groups": [{"id": "g", "label": "G", "fields": [{"id": "name", "label": "N", "type": "text", "required": True}]}]}
    out = render_docx(src, schema, {"name": "A"}, tmp_path / "o.docx")
    assert [p.text for p in Document(out).paragraphs] == ["Hello A"]
    schema["template"]["trim_trailing_blank"] = False
    out = render_docx(src, schema, {"name": "A"}, tmp_path / "o2.docx")
    assert len(Document(out).paragraphs) == 3


@pytest.mark.skipif(not HAS_LO, reason="LibreOffice not installed")
def test_pdf_keeps_images_lossless_at_full_resolution(tmp_path):
    from PIL import Image, ImageDraw
    from pypdf import PdfReader
    img = Image.new("RGB", (2400, 1200), "white"); ImageDraw.Draw(img).text((40, 40), "WATERMARK", fill="gray")
    png = tmp_path / "wm.png"; img.save(png)
    d = Document(); d.add_paragraph("Doc with a large image"); d.add_picture(str(png), width=Inches(6)); src = tmp_path / "img.docx"; d.save(src)
    pdf, _ = convert_to_pdf(src)
    xobjects = [x.get_object() for page in PdfReader(pdf).pages for x in page["/Resources"].get("/XObject", {}).values()]
    images = [x for x in xobjects if x.get("/Subtype") == "/Image"]
    assert images, "no image found in the PDF"
    im = images[0]
    assert "/DCTDecode" not in str(im.get("/Filter"))                   # not JPEG-recompressed
    assert int(im["/Width"]) == 2400 and int(im["/Height"]) == 1200     # not downsampled to 300 dpi
