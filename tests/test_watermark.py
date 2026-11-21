"""PDF-level watermark: config, stamping behind content at full resolution, Word watermark removal."""
import shutil, sys
from pathlib import Path
import pytest, yaml
from docx import Document
from docx.oxml import parse_xml
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from docmaster.pdfconv.watermark import apply_watermark, config_from_schema  # noqa: E402
from docmaster.docgen.ooxml import strip_word_watermarks  # noqa: E402
from docmaster.docgen.linter import lint_template  # noqa: E402
from docmaster.errors import PdfConversionFailed  # noqa: E402

PDF = ROOT / "templates/resume-ats/v1/samples/example-output.pdf"
TPL = ROOT / "templates/resume-ats/v1"


def make_png(path: Path, w=1600, h=800):
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); m = max(1, min(50, w // 8)); ImageDraw.Draw(im).rectangle([m, m, w - 1 - m, h - 1 - m], fill=(200, 30, 30, 255)); im.save(path)


def test_config_defaults_and_validation(tmp_path):
    assert config_from_schema({"template": {}}, tmp_path) is None
    make_png(tmp_path / "wm.png")
    cfg = config_from_schema({"template": {"watermark": {"image": "wm.png", "opacity": 2, "scale": 0.5}}}, tmp_path)
    assert cfg["opacity"] == 1.0 and cfg["scale"] == 0.5 and cfg["rotation"] == 0.0 and cfg["pages"] == "all" and cfg["image"] == tmp_path / "wm.png"
    with pytest.raises(PdfConversionFailed): config_from_schema({"template": {"watermark": {"image": "missing.png"}}}, tmp_path)
    with pytest.raises(PdfConversionFailed): config_from_schema({"template": {"watermark": "wm.png"}}, tmp_path)


def test_watermark_is_stamped_behind_content_at_full_resolution(tmp_path):
    from pypdf import PdfReader
    pdf = tmp_path / "doc.pdf"; shutil.copy(PDF, pdf); make_png(tmp_path / "wm.png")
    before = PdfReader(pdf); n = len(before.pages); text_before = before.pages[0].extract_text()
    apply_watermark(pdf, config_from_schema({"template": {"watermark": {"image": "wm.png", "opacity": 0.2, "scale": 0.7, "rotation": 30}}}, tmp_path))
    after = PdfReader(pdf)
    assert len(after.pages) == n
    assert after.pages[0].extract_text() == text_before                       # content intact and still searchable
    for page in after.pages:
        imgs = [x.get_object() for x in page["/Resources"]["/XObject"].values() if x.get_object().get("/Subtype") == "/Image"]
        assert imgs and int(imgs[0]["/Width"]) == 1600 and int(imgs[0]["/Height"]) == 800 and imgs[0]["/Filter"] == "/FlateDecode"
        content = page.get_contents().get_data()
        assert b"/WmImg Do" in content and content.index(b"/WmImg Do") < content.index(b"BT")   # drawn before the text


def test_first_page_only(tmp_path):
    from pypdf import PdfReader
    pdf = tmp_path / "doc.pdf"; shutil.copy(PDF, pdf); make_png(tmp_path / "wm.png")
    apply_watermark(pdf, config_from_schema({"template": {"watermark": {"image": "wm.png", "pages": "first"}}}, tmp_path))
    pages = PdfReader(pdf).pages
    assert "/WmImg" in str(pages[0]["/Resources"]) and "/WmImg" not in str(pages[1].get("/Resources", {}))


def test_washout_opacity_lightens_pixels(tmp_path):
    from docmaster.pdfconv.watermark import _washed_rgb
    make_png(tmp_path / "wm.png", 4, 4)
    rgb, w, h = _washed_rgb(tmp_path / "wm.png", 0.0); assert rgb == b"\xff" * (4 * 4 * 3)          # opacity 0 → white
    rgb, _, _ = _washed_rgb(tmp_path / "wm.png", 1.0); assert rgb[0:3] == b"\xff\xff\xff" and rgb[(1 * 4 + 1) * 3:(1 * 4 + 1) * 3 + 3] == bytes([200, 30, 30])


VML_WATERMARK = ('<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:v="urn:schemas-microsoft-com:vml" '
                 'xmlns:o="urn:schemas-microsoft-com:office:office"><w:r><w:pict><v:shape id="PowerPlusWaterMarkObject1" o:spid="_x0000_s2049" style="width:400pt;height:300pt">'
                 '<v:imagedata o:title="wm"/></v:shape></w:pict></w:r><w:r><w:t>Header text stays</w:t></w:r></w:p>')


def test_word_watermark_shape_is_removed_from_headers():
    d = Document(); hdr = d.sections[0].header; hdr.is_linked_to_previous = False
    hdr._element.append(parse_xml(VML_WATERMARK))
    assert strip_word_watermarks(d) == 1
    xml = hdr._element.xml
    assert "PowerPlusWaterMarkObject" not in xml and "Header text stays" in xml
    assert strip_word_watermarks(d) == 0


def test_linter_requires_the_watermark_image(tmp_path):
    schema = yaml.safe_load((TPL / "schema.yaml").read_text())
    schema["template"]["watermark"] = {"image": "nope.png"}
    assert "S006" in {f.code for f in lint_template(TPL / "template.docx", schema)}
    d = tmp_path / "t"; shutil.copytree(TPL, d, ignore=shutil.ignore_patterns("samples", "reference.pdf")); make_png(d / "wm.png")
    schema["template"]["watermark"] = {"image": "wm.png"}
    assert "S006" not in {f.code for f in lint_template(d / "template.docx", schema)}
