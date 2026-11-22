"""Targeted OOXML helpers for the things python-docx/docxtpl have no API for.

Each helper edits the package through python-docx's lxml tree, so the rest of the document is
untouched. All are covered by tests/test_ooxml.py.
"""
from __future__ import annotations
import copy
from datetime import datetime, timezone
from docx.document import Document as _Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph


def numbering_ids_in_use(doc: _Document) -> set[str]:
    return {n.get(qn("w:val")) for n in doc.element.body.iter(qn("w:numId"))}


def defined_num_ids(doc: _Document) -> set[str]:
    part = getattr(doc.part, "numbering_part", None)
    if part is None or part.element is None:
        return set()
    return {n.get(qn("w:numId")) for n in part.element.findall(qn("w:num"))}


def restart_numbering(doc: _Document, paragraph: Paragraph, start: int = 1) -> int:
    """Make `paragraph` begin a fresh list sequence (same look as its current list) at `start`.

    Word restarts lists by pointing the paragraph at a new `w:num` that references the same
    `w:abstractNum` and carries a `w:lvlOverride/w:startOverride`. Returns the new numId.
    """
    numpr = paragraph._p.find(f"{qn('w:pPr')}/{qn('w:numPr')}")
    if numpr is None:
        raise ValueError("paragraph is not part of a numbered list")
    old_num_id = numpr.find(qn("w:numId")).get(qn("w:val"))
    ilvl_el = numpr.find(qn("w:ilvl"))
    ilvl = ilvl_el.get(qn("w:val")) if ilvl_el is not None else "0"
    numbering = doc.part.numbering_part.element
    old_num = next(n for n in numbering.findall(qn("w:num")) if n.get(qn("w:numId")) == old_num_id)
    abstract_id = old_num.find(qn("w:abstractNumId")).get(qn("w:val"))
    new_id = max((int(n.get(qn("w:numId"))) for n in numbering.findall(qn("w:num"))), default=0) + 1
    num = OxmlElement("w:num"); num.set(qn("w:numId"), str(new_id))
    ref = OxmlElement("w:abstractNumId"); ref.set(qn("w:val"), abstract_id); num.append(ref)
    ov = OxmlElement("w:lvlOverride"); ov.set(qn("w:ilvl"), ilvl)
    so = OxmlElement("w:startOverride"); so.set(qn("w:val"), str(start)); ov.append(so); num.append(ov)
    numbering.append(num)
    numpr.find(qn("w:numId")).set(qn("w:val"), str(new_id))
    return new_id


def insert_field(paragraph: Paragraph, instruction: str, placeholder: str = "1") -> None:
    """Append a complex field (PAGE, NUMPAGES, DATE \\@ "d MMMM yyyy", …) to a paragraph."""
    def run(child):
        r = OxmlElement("w:r"); r.append(child); paragraph._p.append(r)
    for kind in ("begin",):
        fc = OxmlElement("w:fldChar"); fc.set(qn("w:fldCharType"), kind); run(fc)
    it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = f" {instruction} "; run(it)
    fc = OxmlElement("w:fldChar"); fc.set(qn("w:fldCharType"), "separate"); run(fc)
    t = OxmlElement("w:t"); t.text = placeholder; run(t)
    fc = OxmlElement("w:fldChar"); fc.set(qn("w:fldCharType"), "end"); run(fc)


def mark_fields_dirty(doc: _Document) -> None:
    """Ask Word to refresh all fields on open (LibreOffice recomputes PAGE/NUMPAGES on export anyway)."""
    settings = doc.settings.element
    el = settings.find(qn("w:updateFields"))
    if el is None:
        el = OxmlElement("w:updateFields"); settings.append(el)
    el.set(qn("w:val"), "true")


def set_document_properties(doc: _Document, title: str, author: str = "Papyra", subject: str | None = None) -> None:
    cp = doc.core_properties
    cp.title, cp.author, cp.last_modified_by = title, author, author
    if subject: cp.subject = subject
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cp.created = cp.modified = now
    cp.revision = 1
    cp.comments = ""


def has_tracked_changes(doc: _Document) -> bool:
    body = doc.element.body
    return any(body.iter(qn("w:ins"))) or any(body.iter(qn("w:del")))


def has_comments(doc: _Document) -> bool:
    return any(body for body in doc.element.body.iter(qn("w:commentRangeStart")))


def clone_paragraph_after(paragraph: Paragraph) -> Paragraph:
    el = copy.deepcopy(paragraph._p); paragraph._p.addnext(el)
    return Paragraph(el, paragraph._parent)


def _paragraph_is_blank(p) -> bool:
    """No text, no drawings/pictures, no fields; a page break alone still counts as blank."""
    if "".join(t.text or "" for t in p.iter(qn("w:t"))).strip():
        return False
    for tag in ("w:drawing", "w:pict", "w:fldChar", "w:instrText", "w:sym", "w:object"):
        if next(p.iter(qn(tag)), None) is not None:
            return False
    return True


def trim_trailing_blank(doc: _Document) -> int:
    """Remove empty paragraphs (and explicit page breaks) at the very end of the body: the usual
    cause of an unwanted last page. If the body ends with a table, Word requires one paragraph
    after it, so that one is kept but shrunk to 1 pt with no spacing. Returns the number of changes."""
    body = doc.element.body
    children = [c for c in body if c.tag != qn("w:sectPr")]
    changes = 0
    while children and children[-1].tag == qn("w:p") and _paragraph_is_blank(children[-1]):
        if len(children) >= 2 and children[-2].tag == qn("w:tbl"):
            break
        body.remove(children.pop()); changes += 1
    if children and children[-1].tag == qn("w:p") and len(children) >= 2 and children[-2].tag == qn("w:tbl") and _paragraph_is_blank(children[-1]):
        p = children[-1]
        for br in p.findall(f".//{qn('w:br')}"):
            br.getparent().remove(br)
        ppr = p.find(qn("w:pPr"))
        if ppr is None:
            ppr = OxmlElement("w:pPr"); p.insert(0, ppr)
        for tag in ("w:spacing", "w:rPr"):
            for el in ppr.findall(qn(tag)): ppr.remove(el)
        sp = OxmlElement("w:spacing"); sp.set(qn("w:before"), "0"); sp.set(qn("w:after"), "0"); sp.set(qn("w:line"), "20"); sp.set(qn("w:lineRule"), "exact"); ppr.append(sp)
        rpr = OxmlElement("w:rPr"); sz = OxmlElement("w:sz"); sz.set(qn("w:val"), "2"); rpr.append(sz); ppr.append(rpr)
        changes += 1
    if children and children[-1].tag == qn("w:tbl"):
        p = OxmlElement("w:p"); ppr = OxmlElement("w:pPr")
        sp = OxmlElement("w:spacing"); sp.set(qn("w:before"), "0"); sp.set(qn("w:after"), "0"); sp.set(qn("w:line"), "20"); sp.set(qn("w:lineRule"), "exact"); ppr.append(sp)
        rpr = OxmlElement("w:rPr"); sz = OxmlElement("w:sz"); sz.set(qn("w:val"), "2"); rpr.append(sz); ppr.append(rpr); p.append(ppr)
        sect = body.find(qn("w:sectPr"))
        if sect is not None: sect.addprevious(p)
        else: body.append(p)
        changes += 1
    return changes


def header_footer_elements(doc: _Document):
    """The XML of every header and footer part that already exists. Never goes through
    `section.header`, which *creates* a header part (and needs python-docx's template files)."""
    for rel in doc.part.rels.values():
        if rel.is_external:
            continue
        if rel.reltype.endswith("/header") or rel.reltype.endswith("/footer"):
            el = getattr(rel.target_part, "element", None)
            if el is not None:
                yield el


def strip_word_watermarks(doc: _Document) -> int:
    """Remove Word's own watermark shapes (text or picture) from every existing header, so a
    PDF-level watermark is not doubled. Word names them PowerPlusWaterMarkObject… / WordPictureWatermark…"""
    removed = 0
    V = "{urn:schemas-microsoft-com:vml}"; WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
    for hdr_el in list(header_footer_elements(doc)):
        if True:
            hdr = type("H", (), {"_element": hdr_el})()
            for shape in list(hdr._element.iter(f"{V}shape")):
                ident = (shape.get("id") or "") + (shape.get("{urn:schemas-microsoft-com:office:office}spid") or "")
                if "watermark" in ident.lower():
                    run = shape; 
                    while run is not None and run.tag != qn("w:r"): run = run.getparent()
                    (run if run is not None else shape).getparent().remove(run if run is not None else shape); removed += 1
            for docpr in list(hdr._element.iter(f"{WP}docPr")):
                if "watermark" in (docpr.get("name") or "").lower():
                    run = docpr
                    while run is not None and run.tag != qn("w:r"): run = run.getparent()
                    if run is not None: run.getparent().remove(run); removed += 1
    return removed


def _all_runs(doc: _Document):
    parts = [doc.element.body, *header_footer_elements(doc)]
    for part in parts:
        yield from list(part.iter(qn("w:r")))


def superscript_ordinals(doc: _Document, dates: set[str]) -> int:
    """For each printed date in `dates` that contains an ordinal (12th), raise the suffix as a
    superscript run, as Word's AutoCorrect does. Only the given strings are touched."""
    import re
    if not dates:
        return 0
    changed = 0
    for run in _all_runs(doc):
        texts = run.findall(qn("w:t"))
        if len(texts) != 1 or not texts[0].text:
            continue
        text = texts[0].text
        hit = next((d for d in dates if d in text), None)
        if hit is None:
            continue
        m = re.search(r"(\d{1,2})(st|nd|rd|th)\b", hit)
        if not m:
            continue
        start = text.index(hit) + m.start(2); end = start + len(m.group(2))
        before, suffix, after = text[:start], text[start:end], text[end:]
        rpr = run.find(qn("w:rPr"))
        def make(txt, sup=False):
            r = copy.deepcopy(run)
            for t in r.findall(qn("w:t")): r.remove(t)
            t = OxmlElement("w:t"); t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve"); t.text = txt; r.append(t)
            if sup:
                pr = r.find(qn("w:rPr"))
                if pr is None:
                    pr = OxmlElement("w:rPr"); r.insert(0, pr)
                for old in pr.findall(qn("w:vertAlign")): pr.remove(old)
                va = OxmlElement("w:vertAlign"); va.set(qn("w:val"), "superscript"); pr.append(va)
            return r
        parent = run.getparent(); idx = parent.index(run)
        new = [make(before)] if before else []
        new.append(make(suffix, True))
        if after: new.append(make(after))
        parent.remove(run)
        for i, r in enumerate(new): parent.insert(idx + i, r)
        changed += 1
    return changed
