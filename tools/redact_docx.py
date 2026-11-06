"""Make a structure-only copy of a confidential Word file that is safe to share.

Every letter becomes 'x' (or 'X'), every digit '9'; punctuation, spaces, line lengths, runs,
styles, numbering, tables, headers/footers, images and page setup stay exactly as they are.
Jinja tags ({{ … }}, {% … %}) are preserved so a tagged template can be reviewed too.
Document properties (title/author/comments) are cleared. Images are kept unless --strip-images.

    .venv/bin/python tools/redact_docx.py <in.docx> <out.docx> [--strip-images]
"""
from __future__ import annotations
import argparse, re, sys, zipfile
from pathlib import Path
from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TAG = re.compile(r"(\{\{.*?\}\}|\{%.*?%\})", re.S)


def redact_text(s: str) -> str:
    out = []
    for part in TAG.split(s):
        if TAG.fullmatch(part or ""):
            out.append(part)
        else:
            out.append("".join("9" if c.isdigit() else "X" if c.isupper() else "x" if c.isalpha() else c for c in part))
    return "".join(out)


def redact_part(xml: bytes) -> bytes:
    root = etree.fromstring(xml)
    for t in root.iter(W + "t", W + "delText", W + "instrText"):
        if t.tag == W + "instrText":
            continue                          # field codes (PAGE, NUMPAGES) are not content
        if t.text:
            t.text = redact_text(t.text)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", type=Path); ap.add_argument("dst", type=Path)
    ap.add_argument("--strip-images", action="store_true", help="replace embedded images with 1x1 transparent PNGs")
    a = ap.parse_args()
    blank_png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da6364f8cf0000020001006c4b2e410000000049454e44ae426082")
    with zipfile.ZipFile(a.src) as zin, zipfile.ZipFile(a.dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            n = item.filename
            if n.startswith("word/") and n.endswith(".xml") and any(k in n for k in ("document", "header", "footer", "footnotes", "endnotes", "comments")):
                data = redact_part(data)
            elif n == "docProps/core.xml":
                root = etree.fromstring(data)
                for el in root:
                    if el.tag.endswith(("title", "subject", "creator", "description", "lastModifiedBy", "keywords")):
                        el.text = ""
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            elif a.strip_images and n.startswith("word/media/"):
                data = blank_png
            zout.writestr(item, data)
    print(f"redacted copy written to {a.dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
