"""Template linter: catches template-authoring mistakes before they reach users.

Runs in CI over every bundled template (tests/test_templates_lint.py) and from
`tools/lint_templates.py`. Each finding has a stable code so docs can explain it.
"""
from __future__ import annotations
import re, zipfile
from dataclasses import dataclass
from pathlib import Path
from docx import Document
from docxtpl import DocxTemplate
from jinja2 import Environment, StrictUndefined, TemplateSyntaxError
from .ooxml import defined_num_ids, has_comments, has_tracked_changes, numbering_ids_in_use
from .render import RESERVED_IDS, SCALAR_TYPES, link_name

SMART = {"“{{": "L001", "}}”": "L001", "‘{{": "L001", "{{“": "L001"}
TAG_RE = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.S)


@dataclass
class Finding:
    code: str
    level: str          # error | warning
    message: str
    part: str = "word/document.xml"

    def __str__(self):
        return f"[{self.level}] {self.code} {self.part}: {self.message}"


def _xml_parts(docx: Path) -> dict[str, str]:
    with zipfile.ZipFile(docx) as z:
        return {n: z.read(n).decode("utf8", "replace") for n in z.namelist()
                if n.startswith("word/") and n.endswith(".xml") and "/theme/" not in n and "fontTable" not in n}


def lint_template(docx: Path, schema: dict) -> list[Finding]:
    f: list[Finding] = []
    parts = _xml_parts(docx)
    doc = Document(docx)

    # --- schema sanity ---
    fields = [x for g in schema.get("groups", []) for x in g.get("fields", [])]
    ids = [x["id"] for x in fields]
    for dup in {i for i in ids if ids.count(i) > 1}:
        f.append(Finding("S001", "error", f"duplicate field id '{dup}'", "schema.yaml"))
    for x in fields:
        for sub in x.get("item_fields", []) + [x]:
            if sub["id"] in RESERVED_IDS:
                f.append(Finding("S002", "error", f"field id '{sub['id']}' shadows a dict attribute / Jinja name", "schema.yaml"))
            if sub["type"] not in SCALAR_TYPES | {"group_list", "text_list"}:
                f.append(Finding("S003", "error", f"field '{sub['id']}' has unknown type '{sub['type']}'", "schema.yaml"))
            if sub["type"] == "select" and not sub.get("options"):
                f.append(Finding("S004", "error", f"select field '{sub['id']}' has no options", "schema.yaml"))
    wm = schema.get("template", {}).get("watermark")
    if wm is not None:
        if not isinstance(wm, dict) or not wm.get("image"):
            f.append(Finding("S006", "error", "template.watermark needs an 'image' file name", "schema.yaml"))
        elif __import__("docmaster.pdfconv.watermark", fromlist=["resolve_asset"]).resolve_asset(docx.parent, wm["image"]) is None:
            f.append(Finding("S006", "error", f"watermark image '{wm['image']}' not found in the template folder or in templates/_assets", "schema.yaml"))
        elif Path(wm["image"]).suffix.lower() not in (".png", ".jpg", ".jpeg", ".svg"):
            f.append(Finding("S006", "error", f"watermark image must be PNG, JPEG or SVG, not '{Path(wm['image']).suffix}'", "schema.yaml"))
    if not schema.get("template", {}).get("output_filename"):
        f.append(Finding("S005", "warning", "template.output_filename not set; a generic name will be used", "schema.yaml"))

    # --- document hygiene ---
    if has_tracked_changes(doc): f.append(Finding("D001", "error", "template contains tracked changes; accept or reject them"))
    if has_comments(doc): f.append(Finding("D002", "error", "template contains comments; remove them"))
    missing_nums = numbering_ids_in_use(doc) - defined_num_ids(doc) - {"0"}
    if missing_nums: f.append(Finding("D003", "error", f"paragraphs reference undefined numbering ids {sorted(missing_nums)}"))
    if any(n.startswith("customXML/") for n in zipfile.ZipFile(docx).namelist()):
        f.append(Finding("D004", "warning", "package contains customXML parts (editor round-trip data); drop them"))

    # --- tag syntax, per part (after docxtpl's run normalisation, which is what will actually render) ---
    tpl = DocxTemplate(docx)
    env = Environment(undefined=StrictUndefined, autoescape=True)
    for name, xml in parts.items():
        for s, code in SMART.items():
            if s in xml: f.append(Finding(code, "error", f"smart quote next to a tag ('{s}'): Word auto-corrected the template", name))
        plain = re.sub(r"<[^>]+>", "", xml)
        if plain.count("{{") != plain.count("}}") or plain.count("{%") != plain.count("%}"):
            f.append(Finding("T001", "error", "unbalanced {{ }} or {% %} tags", name))
        for m in re.finditer(r"\{\{r\s+[^}]*\}\}([^<]+)<", xml):
            if TAG_RE.sub("", m.group(1)).strip():          # control tags ({% endif %}) emit nothing
                f.append(Finding("T003", "error", f"text follows a {{{{r }}}} tag inside the same run: '{m.group(1)[:30]}' loses its formatting", name))
    try:
        used = tpl.get_undeclared_template_variables(env)
    except TemplateSyntaxError as e:
        f.append(Finding("T002", "error", f"Jinja syntax error: {e}"))
        return f

    # --- template ↔ schema agreement ---
    links = {link_name(x["id"]) for x in fields if x["type"] == "url"}
    non_print = {x["id"] for g in schema.get("groups", []) if g.get("print") is False for x in g.get("fields", [])}
    printable = set(ids) | links
    for v in sorted(used - printable): f.append(Finding("M001", "error", f"template uses '{v}' which is not a schema field"))
    for v in sorted(printable - used - non_print - links - {x["id"] for x in fields if x["type"] == "url" and link_name(x["id"]) in used}): f.append(Finding("M002", "error", f"schema field '{v}' is never used by the template"))
    for x in fields:
        if x["type"] == "url" and link_name(x["id"]) not in used and x["id"] in used:
            f.append(Finding("M003", "warning", f"url field '{x['id']}' is printed as plain text; use {{{{r {link_name(x['id'])} }}}} for a clickable link"))
    return f


def cross_template_findings(schemas: dict[str, dict]) -> list[Finding]:
    """M004: the same field id with different types across templates is asked separately when the
    templates are generated together; usually a sign that one of them should be renamed."""
    types: dict[str, dict[str, str]] = {}
    for name, schema in schemas.items():
        for g in schema.get("groups", []):
            for f in g.get("fields", []):
                types.setdefault(f["id"], {})[name] = f["type"]
    out = []
    for fid, by in sorted(types.items()):
        if len(set(by.values())) > 1:
            detail = ", ".join(f"{n}: {t}" for n, t in sorted(by.items()))
            out.append(Finding("M004", "warning", f"field '{fid}' has different types across templates ({detail}); it is asked separately in a batch", "schema.yaml"))
    return out


def lint_catalogue(templates_dir: Path) -> dict[str, list[Finding]]:
    import yaml
    out = {}; schemas = {}
    for schema_path in sorted(templates_dir.glob("*/v*/schema.yaml")):
        schema = yaml.safe_load(schema_path.read_text(encoding="utf8"))
        docx = schema_path.parent / schema["template"]["file"]
        key = f"{schema['template']['id']} v{schema['template']['version']}"
        out[key] = lint_template(docx, schema); schemas[key] = schema
    cross = cross_template_findings(schemas)
    if cross:
        out["(across templates)"] = cross
    return out
