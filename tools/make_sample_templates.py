"""Create five small sample templates (fictional data) for trying out watermarks, date formats and
batches. They go into the user templates folder by default, or any folder you name:

    .venv/bin/python tools/make_sample_templates.py                 # → ~/Documents/Papyra/templates
    .venv/bin/python tools/make_sample_templates.py /path/to/folder

Each template: template.docx (tagged), schema.yaml (5-6 fields, watermark, its own date format),
values.example.yaml. A shared watermark lives in <folder>/_assets/sample-watermark.svg.
"""
from __future__ import annotations
import sys
from pathlib import Path
import yaml
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

WATERMARK_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400" viewBox="0 0 800 400">
  <rect x="20" y="20" width="760" height="360" rx="40" fill="none" stroke="#1d3557" stroke-width="18"/>
  <text x="400" y="235" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="150" font-weight="bold" fill="#e63946">SAMPLE</text>
</svg>
"""

EMAIL_GROUP = {"id": "email_draft", "label": "Email draft", "print": False, "fields": [
    {"id": "recipient_email", "label": "Recipient", "type": "email", "required": True},
    {"id": "email_subject", "label": "Subject", "type": "text", "required": True, "default": "{__name__} — {full_name}"},
    {"id": "email_body", "label": "Message", "type": "multiline", "required": True, "default": "Dear {full_name},\n\nPlease find the document attached.\n\nKind regards"}]}

TEMPLATES = [
    {"id": "offer-letter", "name": "Offer letter", "date_format": "MMMM Do, YYYY", "wm": {"rotation": 30, "opacity": 0.12},
     "fields": [("full_name", "Full name", "text"), ("email", "Email", "email"), ("position", "Position", "text"),
                ("joining_date", "Joining date", "date"), ("annual_salary", "Annual salary (INR)", "number"),
                ("probation_months", "Probation", "select", ["3", "6"])],
     "body": [("H", "Offer of employment"), ("P", "Dear {{ full_name }},"),
              ("P", "We are pleased to offer you the position of {{ position }}. Your joining date will be {{ joining_date }}."),
              ("P", "Your annual salary will be INR {{ annual_salary }} with a probation period of {{ probation_months }} months."),
              ("P", "Please confirm by replying to this letter at {{ email }}."), ("P", "Date: {{ joining_date | date(\"DD/MM/YYYY\") }}")],
     "example": {"full_name": "Asha Verma", "email": "asha@example.com", "position": "Frontend Engineer", "joining_date": "2026-03-12", "annual_salary": 1850000, "probation_months": "6"}},
    {"id": "nda", "name": "Non-disclosure agreement", "date_format": "Do MMMM YYYY", "wm": {"rotation": 0, "opacity": 0.1, "position": "center"},
     "fields": [("full_name", "Full name", "text"), ("email", "Email", "email"), ("company_name", "Company", "text"),
                ("effective_date", "Effective date", "date"), ("term_months", "Term (months)", "number"), ("confidential_note", "Scope of confidential information", "multiline")],
     "body": [("H", "Non-disclosure agreement"), ("P", "This agreement is made on {{ effective_date }} between {{ company_name }} and {{ full_name }} ({{ email }})."),
              ("P", "Confidential information covers: {{ confidential_note }}"), ("P", "The obligations in this agreement last for {{ term_months }} months from the effective date.")],
     "example": {"full_name": "Asha Verma", "email": "asha@example.com", "company_name": "Example Technologies Pvt Ltd", "effective_date": "2026-01-02", "term_months": 24, "confidential_note": "Product roadmaps, source code, customer lists and pricing."}},
    {"id": "experience-letter", "name": "Experience letter", "date_format": "D MMM YYYY", "wm": {"rotation": 45, "opacity": 0.15, "scale": 0.8},
     "fields": [("full_name", "Full name", "text"), ("email", "Email", "email"), ("designation", "Designation", "text"),
                ("start_date", "Start date", "date"), ("end_date", "End date", "date"), ("remarks", "Remarks", "multiline")],
     "body": [("H", "To whom it may concern"), ("P", "This is to certify that {{ full_name }} ({{ email }}) was employed as {{ designation }} from {{ start_date }} to {{ end_date }}."),
              ("P", "{{ remarks }}"), ("P", "We wish them success in their future endeavours.")],
     "example": {"full_name": "Asha Verma", "email": "asha@example.com", "designation": "Senior Engineer", "start_date": "2021-07-01", "end_date": "2026-02-28", "remarks": "A dependable colleague who led the platform migration."}},
    {"id": "invoice", "name": "Invoice", "date_format": "DD/MM/YYYY", "wm": {"rotation": 0, "opacity": 0.08, "position": "top", "scale": 0.4},
     "fields": [("full_name", "Client name", "text"), ("email", "Client email", "email"), ("invoice_number", "Invoice number", "text"),
                ("invoice_date", "Invoice date", "date"), ("amount", "Amount (INR)", "number"), ("description", "Description", "multiline")],
     "body": [("H", "Invoice {{ invoice_number }}"), ("P", "Date: {{ invoice_date }}"), ("P", "Billed to: {{ full_name }} ({{ email }})"),
              ("P", "{{ description }}"), ("P", "Amount due: INR {{ amount }}"), ("P", "Due by {{ invoice_date | date(\"MMMM D, YYYY\") }} plus 30 days.")],
     "example": {"full_name": "Example Technologies Pvt Ltd", "email": "accounts@example.com", "invoice_number": "INV-2026-0042", "invoice_date": "2026-03-05", "amount": 125000, "description": "Consulting services for March 2026."}},
    {"id": "meeting-minutes", "name": "Meeting minutes", "date_format": "dddd, MMMM Do, YYYY", "wm": {"rotation": 20, "opacity": 0.1, "black_white": True},
     "fields": [("full_name", "Chair", "text"), ("email", "Chair email", "email"), ("meeting_date", "Meeting date", "date"),
                ("location", "Location", "text"), ("agenda", "Agenda items", "text_list"), ("decisions", "Decisions", "multiline")],
     "body": [("H", "Minutes of meeting"), ("P", "Held on {{ meeting_date }} at {{ location }}, chaired by {{ full_name }} ({{ email }})."),
              ("P", "Agenda:"), ("LOOP", "agenda", "a", "• {{ a }}"), ("P", "Decisions: {{ decisions }}")],
     "example": {"full_name": "Asha Verma", "email": "asha@example.com", "meeting_date": "2026-03-20", "location": "Pune office, room 4", "agenda": ["Release plan", "Hiring", "Budget"], "decisions": "Release moves to April; two engineers to be hired."}},
]


def build_docx(t: dict, path: Path) -> None:
    d = Document()
    st = d.styles["Normal"]; st.font.name = "Arial"; st.font.size = Pt(11)
    for item in t["body"]:
        kind = item[0]
        if kind == "H":
            p = d.add_paragraph(); r = p.add_run(item[1]); r.bold = True; r.font.size = Pt(18); p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        elif kind == "P":
            d.add_paragraph(item[1])
        elif kind == "LOOP":
            _, var, alias, line = item
            d.add_paragraph(f"{{%p for {alias} in {var} %}}"); d.add_paragraph(line); d.add_paragraph("{%p endfor %}")
    d.add_paragraph("Generated with Papyra sample template: " + t["name"])
    d.save(path)


def build_schema(t: dict) -> dict:
    fields = []
    for f in t["fields"]:
        fid, label, ftype = f[0], f[1], f[2]
        fd = {"id": fid, "label": label, "type": ftype, "required": True}
        if ftype == "text": fd["validation"] = {"max_length": 120}
        if ftype == "multiline": fd["validation"] = {"max_length": 1000}
        if ftype == "number": fd["validation"] = {"min": 0}
        if ftype == "select": fd["options"] = [{"value": v, "label": f"{v} months"} for v in f[3]]
        if ftype == "text_list": fd["validation"] = {"min_items": 1, "max_items": 10}; fd["item"] = {"type": "text", "validation": {"max_length": 200}}
        fields.append(fd)
    email = yaml.safe_load(yaml.safe_dump(EMAIL_GROUP)); email["fields"][1]["default"] = email["fields"][1]["default"].replace("{__name__}", t["name"])
    return {"template": {"id": t["id"], "version": 1, "name": t["name"], "description": f"Sample {t['name'].lower()} with a watermark and the date format {t['date_format']}.",
                         "file": "template.docx", "output_filename": "{full_name}-" + t["name"].replace(" ", "-") + "-{date}",
                         "expected_pages": {"min": 1, "max": 3}, "essential_text": ["full_name"], "date_format": t["date_format"],
                         "watermark": {"image": "sample-watermark.svg", "grayscale": True, "scale": 0.6, "opacity": 0.15, **t["wm"]}},
            "groups": [{"id": "details", "label": "Details", "fields": fields}, email]}


def main(root: Path, watermark: Path | None = None) -> list[Path]:
    """`watermark`: your own SVG/PNG/JPEG logo; it is copied to `_assets/logo.<ext>` and used by every sample."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "_assets").mkdir(exist_ok=True); (root / "_assets" / "sample-watermark.svg").write_text(WATERMARK_SVG, encoding="utf8")
    image_name = "sample-watermark.svg"
    if watermark:
        image_name = "logo" + watermark.suffix.lower()
        (root / "_assets" / image_name).write_bytes(watermark.read_bytes())
    made = []
    for t in TEMPLATES:
        d = root / t["id"] / "v1"; d.mkdir(parents=True, exist_ok=True)
        build_docx(t, d / "template.docx")
        schema = build_schema(t); schema["template"]["watermark"]["image"] = image_name
        (d / "schema.yaml").write_text("# Sample template generated by tools/make_sample_templates.py\n" + yaml.safe_dump(schema, sort_keys=False, allow_unicode=True), encoding="utf8")
        example = {**t["example"], "recipient_email": "someone@example.com", "email_subject": f"{t['name']} — {t['example']['full_name']}",
                   "email_body": f"Dear {t['example']['full_name']},\n\nPlease find the document attached.\n\nKind regards"}
        (d / "values.example.yaml").write_text(yaml.safe_dump(example, sort_keys=False, allow_unicode=True, default_style=None), encoding="utf8")
        made.append(d)
    return made


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", nargs="?", type=Path, default=Path.home() / "Documents" / "Papyra" / "templates")
    ap.add_argument("--watermark", type=Path, default=None, help="your own logo (SVG/PNG/JPEG) to use instead of the SAMPLE stamp")
    a = ap.parse_args(); target = a.folder.expanduser()
    for d in main(target, a.watermark):
        print("created", d)
    from docmaster.docgen.linter import lint_catalogue
    problems = 0
    for name, findings in lint_catalogue(target).items():
        errs = [str(f) for f in findings if f.level == "error"]
        if errs: problems += 1; print(f"{name}: " + "; ".join(errs))
    print("lint:", "OK" if not problems else f"{problems} template(s) with errors")
