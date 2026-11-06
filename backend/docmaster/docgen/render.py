"""DOCX generation: schema validation → docxtpl render → post-render checks.

Rules enforced here (each one came from a Phase-1 finding):
  * every schema field is validated (required, max_length, min/max_items, pattern, email/url shape)
  * field ids must not shadow dict attributes (Jinja resolves `s.items` as the method)
  * every variable the template uses must be in the schema, and vice-versa (no silent gaps)
  * StrictUndefined + autoescape: a missing value raises, XML special characters are escaped
  * url fields automatically get a hyperlink variable: `github_url` -> `github_link`
  * post-render: no Jinja tag left in any part; output re-opens with python-docx
"""
from __future__ import annotations
import re, zipfile
from pathlib import Path
from docx import Document
from docxtpl import DocxTemplate, RichText
from jinja2 import Environment, StrictUndefined
from ..errors import ValidationError, TemplateInvalid, DocxGenerationFailed

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SCALAR_TYPES = {"text", "multiline", "email", "url", "date", "number", "select", "checkbox"}
URL_RE = re.compile(r"^https?://[^\s]+$")
RESERVED_IDS = set(dir(dict)) | {"loop", "r"}


def link_name(field_id: str) -> str:
    return re.sub(r"_url$", "", field_id) + "_link"


def _check_scalar(f, v, path, errors):
    t = f["type"]; rules = f.get("validation", {})
    if t == "checkbox":
        if v not in (None, True, False): errors.append(f"{path}: expected true/false")
        return
    if v in (None, ""):
        if f.get("required"): errors.append(f"{path}: required")
        return
    if t == "number":
        if isinstance(v, bool) or not isinstance(v, (int, float)): errors.append(f"{path}: expected a number"); return
        if "min" in rules and v < rules["min"]: errors.append(f"{path}: less than {rules['min']}")
        if "max" in rules and v > rules["max"]: errors.append(f"{path}: greater than {rules['max']}")
        return
    if not isinstance(v, str): errors.append(f"{path}: expected text"); return
    if t == "date":
        if not DATE_RE.match(v): errors.append(f"{path}: expected a date as YYYY-MM-DD")
        else:
            from datetime import date
            try: date.fromisoformat(v)
            except ValueError: errors.append(f"{path}: not a real date")
        return
    if t == "select":
        allowed = [o["value"] if isinstance(o, dict) else o for o in f.get("options", [])]
        if v not in allowed: errors.append(f"{path}: must be one of {allowed}")
        return
    if "max_length" in rules and len(v) > rules["max_length"]: errors.append(f"{path}: longer than {rules['max_length']}")
    if "pattern" in rules and not re.search(rules["pattern"], v): errors.append(f"{path}: does not match {rules['pattern']}")
    if t == "email" and not EMAIL_RE.match(v): errors.append(f"{path}: not a valid email address")
    if t == "url" and not URL_RE.match(v): errors.append(f"{path}: must start with http:// or https://")


def _check_field(f, v, path, errors):
    t = f["type"]; rules = f.get("validation", {})
    if t in ("group_list", "text_list"):
        if not v:
            if f.get("required"): errors.append(f"{path}: at least one item required")
            return
        if not isinstance(v, list): errors.append(f"{path}: expected a list"); return
        if "min_items" in rules and len(v) < rules["min_items"]: errors.append(f"{path}: fewer than {rules['min_items']} items")
        if "max_items" in rules and len(v) > rules["max_items"]: errors.append(f"{path}: more than {rules['max_items']} items")
        for i, item in enumerate(v):
            if t == "group_list":
                if not isinstance(item, dict): errors.append(f"{path}[{i}]: expected an object"); continue
                for sf in f["item_fields"]:
                    _check_field(sf, item.get(sf["id"]), f"{path}[{i}].{sf['id']}", errors)
            else:
                _check_scalar({**f["item"], "required": True}, item, f"{path}[{i}]", errors)
    else:
        _check_scalar(f, v, path, errors)


def schema_fields(schema) -> list[dict]:
    fields = [f for g in schema["groups"] for f in g["fields"]]
    for f in fields:
        for sub in f.get("item_fields", []) + [f]:
            if sub["id"] in RESERVED_IDS:
                raise TemplateInvalid(f"field id '{sub['id']}' is reserved (shadows a dict attribute or Jinja name)")
            if sub["type"] not in SCALAR_TYPES | {"group_list", "text_list"}:
                raise TemplateInvalid(f"field '{sub['id']}' has unknown type '{sub['type']}'")
    return fields


def validate(schema, values) -> list[dict]:
    fields = schema_fields(schema)
    errors: list[str] = []
    for f in fields:
        _check_field(f, values.get(f["id"]), f["id"], errors)
    if errors:
        raise ValidationError(data={"errors": errors})
    return fields


def check_template_against_schema(tpl: DocxTemplate, schema, fields, env) -> None:
    used = tpl.get_undeclared_template_variables(env)
    links = {link_name(f["id"]) for f in fields if f["type"] == "url"}
    printable = {f["id"] for f in fields} | links
    non_print = {f["id"] for g in schema["groups"] if g.get("print") is False for f in g["fields"]}
    unknown = used - printable
    unused = printable - used - non_print - links - {x["id"] for x in fields if x["type"] == "url" and link_name(x["id"]) in used}
    if unknown: raise TemplateInvalid(f"template uses variables not in schema: {sorted(unknown)}")
    if unused: raise TemplateInvalid(f"schema fields never used by template: {sorted(unused)}")


def build_context(tpl, fields, values):
    ctx = {}
    for f in fields:
        v = values.get(f["id"])
        ctx[f["id"]] = v if v is not None else ("" if f["type"] not in ("checkbox", "number") else None)
        if f["type"] == "url" and v:
            label = re.sub(r"^https?://(www\.)?", "", v).rstrip("/")
            rt = RichText(); rt.add(label, url_id=tpl.build_url_id(v), color="0563c1", underline=True, size=20)
            ctx[link_name(f["id"])] = rt
    return ctx


def render_docx(template_docx: Path, schema: dict, values: dict, out: Path) -> Path:
    fields = validate(schema, values)
    tpl = DocxTemplate(template_docx)
    env = Environment(undefined=StrictUndefined, autoescape=True)
    check_template_against_schema(tpl, schema, fields, env)
    try:
        tpl.render(build_context(tpl, fields, values), jinja_env=env)
        out.parent.mkdir(parents=True, exist_ok=True)
        tpl.save(out)
    except Exception as e:  # noqa: BLE001
        raise DocxGenerationFailed(f"rendering failed: {type(e).__name__}: {e}")
    with zipfile.ZipFile(out) as z:
        for name in z.namelist():
            if name.endswith(".xml") and re.search(rb"\{\{|\{%", z.read(name)):
                out.unlink(missing_ok=True)
                raise DocxGenerationFailed(f"unrendered tag left in {name}")
    Document(out)  # must re-open
    return out
