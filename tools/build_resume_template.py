"""Build templates/resume-ats/v1/template.docx from the untouched source resume.

Reproducible template authoring: every edit is explicit code, so the template can be
rebuilt whenever the source or the tag layout changes. The source file is only read.

Fixes applied relative to the source (see docs/templates/resume-ats-analysis.md §2):
  1. a real tab character between title/degree and the dates (the tab stop existed, the tab didn't)
  2. the two stray empty paragraphs after the second experience entry are dropped
  3. Google Docs round-trip customXML part dropped; document properties set
  4. job-title lines get 'keep with next' so a title is never orphaned at a page bottom
"""
from __future__ import annotations
import copy, sys
from pathlib import Path
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

SRC = Path("private/source/resume-source.docx")   # confidential source, kept outside git (private/ is ignored)
DST = Path("templates/resume-ats/v1/template.docx")


# ---------- low-level helpers (python-docx has no API for most of this) ----------
def text_runs(p):
    return [r for r in p.runs if r.text]

def set_text(p, *texts):
    """Assign texts to the paragraph's non-empty runs in order (formatting kept)."""
    runs = text_runs(p)
    assert len(runs) >= len(texts), f"paragraph has {len(runs)} text runs, need {len(texts)}: {p.text!r}"
    for r, t in zip(runs, texts):
        r.text = t
    for r in runs[len(texts):]:
        r._r.getparent().remove(r._r)

def new_para_like(p, text, spacing_after=None):
    """Clone p (pPr included), replace its runs with one plain-text run."""
    el = copy.deepcopy(p._p)
    for r in el.findall(qn("w:r")) + el.findall(qn("w:hyperlink")):
        el.remove(r)
    r = OxmlElement("w:r"); t = OxmlElement("w:t"); t.set(qn("xml:space"), "preserve"); t.text = text
    r.append(t); el.append(r)
    if spacing_after is not None:
        el.find(qn("w:pPr")).find(qn("w:spacing")).set(qn("w:after"), str(spacing_after))
    return el

def tag_before(p, tag):  p._p.addprevious(new_para_like(p, tag))
def tag_after(p, tag):   p._p.addnext(new_para_like(p, tag))

def insert_tab_run(p, after_run_index):
    r = OxmlElement("w:r"); r.append(OxmlElement("w:tab"))
    text_runs(p)[after_run_index]._r.addnext(r)

def remove(p):
    p._p.getparent().remove(p._p)

def loop_with_last_variant(p, for_tag, last_condition, last_after):
    """Wrap paragraph p in a loop where the last iteration uses a larger 'space after'.

    Produces:  {%p for %} {%p if <last_condition> %} p(after=last_after) {%p else %} p {%p endif %} {%p endfor %}
    Word's inter-paragraph spacing is per paragraph, so this reproduces the source exactly.
    """
    last = copy.deepcopy(p._p)
    last.find(qn("w:pPr")).find(qn("w:spacing")).set(qn("w:after"), str(last_after))
    tag_before(p, for_tag)
    tag_before(p, f"{{%p if {last_condition} %}}")
    p._p.addprevious(last)
    tag_before(p, "{%p else %}")
    tag_after(p, "{%p endif %}")
    # endfor goes after the endif paragraph
    p._p.getnext().addnext(new_para_like(p, "{%p endfor %}"))


def build(src: Path, dst: Path) -> None:
    doc = Document(src)
    P = doc.paragraphs  # snapshot of the 54 source paragraphs; indices from the analysis

    # --- header block ---
    set_text(P[0], "{{ full_name|upper }}")
    set_text(P[1], "{{ headline }}")
    contact = P[2]
    for h in contact._p.findall(qn("w:hyperlink")):          # source links are static; links are generated per document
        contact._p.remove(h)
    # docxtpl re-opens a run without rPr after a {{r }} tag, so each link tag must end its run
    sep = text_runs(contact)[1]; sep._r.addnext(copy.deepcopy(sep._r))
    set_text(contact, "{{ email }}  |  {{ phone }}",
             "{% if github_url %}  |  {{r github_link }}{% endif %}",
             "{% if linkedin_url %}  |  {{r linkedin_link }}{% endif %}")
    for rid in ("rId7", "rId8"):
        doc.part.drop_rel(rid)

    # --- summary ---
    set_text(P[4], "{{ summary }}")

    # --- skills: one formatted paragraph in a loop; 'Other' line optional ---
    set_text(P[6], "{{ s.category }}: ", "{{ s.skill_items }}")
    loop_with_last_variant(P[6], "{%p for s in skills %}", "loop.last and not skills_other", 160)
    for i in range(7, 14):
        remove(P[i])
    set_text(P[14], "Other: {{ skills_other }}")
    tag_before(P[14], "{%p if skills_other %}"); tag_after(P[14], "{%p endif %}")

    # --- experience: nested loop (jobs x bullets) ---
    title, bullet = P[16], P[17]
    set_text(title, "{{ job.title }} — {{ job.company }}", "{{ job.start }} – {{ job.end }}")
    insert_tab_run(title, 0)                                   # fix 1
    title.paragraph_format.keep_with_next = True               # fix 4: a job title never ends a page alone
    tag_before(title, "{%p for job in experience %}")
    tag_before(title, "{%p set job_last = loop.last %}")
    set_text(bullet, "{{ b }}")
    loop_with_last_variant(bullet, "{%p for b in job.bullets %}", "loop.last and job_last", 160)
    bullet._p.getnext().getnext().addnext(new_para_like(bullet, "{%p endfor %}"))  # closes the job loop
    for i in range(18, 43):                                    # remaining jobs, incl. the 2 empty paras (fix 2)
        remove(P[i])

    # --- achievements (optional section) ---
    set_text(P[44], "{{ a }}")
    loop_with_last_variant(P[44], "{%p for a in achievements %}", "loop.last", 160)
    remove(P[45]); remove(P[46])
    tag_before(P[43], "{%p if achievements %}")
    P[44]._p.getnext().getnext().addnext(new_para_like(P[44], "{%p endif %}"))

    # --- education ---
    set_text(P[48], "{{ e.degree }}, {{ e.institution }}", "{{ e.start_year }} – {{ e.end_year }}")
    insert_tab_run(P[48], 0)                                   # fix 1
    loop_with_last_variant(P[48], "{%p for e in education %}", "loop.last", 160)
    remove(P[49])

    # --- optional one-paragraph sections ---
    set_text(P[51], "{{ domain_expertise }}")
    tag_before(P[50], "{%p if domain_expertise %}"); tag_after(P[51], "{%p endif %}")
    set_text(P[53], "{{ languages }}")
    tag_before(P[52], "{%p if languages %}"); tag_after(P[53], "{%p endif %}")

    # --- package hygiene (fix 3) ---
    for rel in list(doc.part.rels.values()):
        if rel.reltype.endswith("/customXml"):
            doc.part.drop_rel(rel.rId)
    cp = doc.core_properties
    cp.title = "Resume (ATS) — template v1"; cp.author = "Papyra"; cp.comments = "Bundled template. Do not edit generated copies back into this file."

    dst.parent.mkdir(parents=True, exist_ok=True)
    doc.save(dst)
    print(f"built {dst} from {src}")


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else SRC, Path(sys.argv[2]) if len(sys.argv) > 2 else DST)
