"""Structural diff of two .docx files: paragraph properties, run formatting, text, numbering, sections.

Usage: docx_structdiff.py a.docx b.docx   (exit 0 when identical)
Formatting flags with w:val="0"/"none"/"false" are treated as off, so Google-Docs-style
explicit-off attributes do not produce noise.
"""
from __future__ import annotations
import difflib, sys, zipfile
from lxml import etree
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
OFF = {"0", "none", "false"}

def on(rpr, tag):
    if rpr is None: return False
    e = rpr.find(W + tag)
    return e is not None and e.get(W + "val", "1") not in OFF

def val(el, tag, attr="val"):
    if el is None: return None
    e = el.find(W + tag); return None if e is None else e.get(W + attr)

def run_sig(r, link=None):
    rpr = r.find(W + "rPr")
    text = "".join(("\t" if c.tag == W + "tab" else (c.text or "")) for c in r if c.tag in (W + "t", W + "tab"))
    if not text: return None
    fonts = rpr.find(W + "rFonts") if rpr is not None else None
    sig = dict(font=fonts.get(W + "ascii") if fonts is not None else None, sz=val(rpr, "sz"),
               b=on(rpr, "b"), i=on(rpr, "i"), u=(val(rpr, "u") not in (None, "none")), color=val(rpr, "color"))
    if link: sig["link"] = link
    return f"{text!r} {sig}"

def para_lines(doc, rels):
    out = []
    for p in doc.find(W + "body").iter(W + "p"):
        ppr = p.find(W + "pPr")
        numpr = ppr.find(W + "numPr") if ppr is not None else None
        sp = ppr.find(W + "spacing") if ppr is not None else None
        ind = ppr.find(W + "ind") if ppr is not None else None
        tabs = [(t.get(W + "val"), t.get(W + "pos")) for t in ppr.iter(W + "tab")] if ppr is not None else []
        head = dict(style=val(ppr, "pStyle"), num=(val(numpr, "ilvl"), val(numpr, "numId")) if numpr is not None else None,
                    jc=val(ppr, "jc"), spacing={k.split("}")[1]: v for k, v in sp.attrib.items()} if sp is not None else None,
                    ind={k.split("}")[1]: v for k, v in ind.attrib.items()} if ind is not None else None, tabs=tabs)
        out.append("P " + str(head))
        for c in p:
            if c.tag == W + "r":
                s = run_sig(c)
                if s: out.append("   R " + s)
            elif c.tag == W + "hyperlink":
                target = rels.get(c.get(R + "id"))
                for r in c.findall(W + "r"):
                    s = run_sig(r, link=target)
                    if s: out.append("   R " + s)
    return out

def load(path):
    z = zipfile.ZipFile(path)
    doc = etree.fromstring(z.read("word/document.xml"))
    rels = {r.get("Id"): r.get("Target") for r in etree.fromstring(z.read("word/_rels/document.xml.rels"))}
    lines = para_lines(doc, rels)
    for s in doc.iter(W + "sectPr"):
        pg, mg = s.find(W + "pgSz"), s.find(W + "pgMar")
        lines.append("SECT " + str({k.split('}')[1]: v for e in (pg, mg) if e is not None for k, v in e.attrib.items()}))
    if "word/numbering.xml" in z.namelist():
        n = etree.fromstring(z.read("word/numbering.xml"))
        for a in n.findall(W + "abstractNum"):
            lines.append("NUM " + a.get(W + "abstractNumId") + " " + str([(val(l, "numFmt"), val(l, "lvlText")) for l in a.findall(W + "lvl")][:3]))
    lines.append("PARTS " + str(sorted(n for n in z.namelist() if not n.startswith("docProps"))))
    return lines

if __name__ == "__main__":
    a, b = load(sys.argv[1]), load(sys.argv[2])
    diff = list(difflib.unified_diff(a, b, sys.argv[1], sys.argv[2], lineterm="", n=0))
    print("\n".join(diff) if diff else "IDENTICAL structure")
    print(f"\n{len(a)} vs {len(b)} structural lines; {sum(1 for l in diff if l[:1] in '+-' and not l.startswith(('+++','---')))} differing")
    sys.exit(1 if diff else 0)
