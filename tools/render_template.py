"""Render a template directory (template.docx + schema.yaml) with a values file — thin CLI over
backend/docmaster/docgen/render.py.  Usage: render_template.py <template_dir> <values.yaml> <out.docx>"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import yaml
from docmaster.docgen.render import render_docx, RESERVED_IDS  # noqa: E402,F401
from docmaster.errors import ValidationError, TemplateInvalid, DocMasterError  # noqa: E402,F401


def render(template_dir: Path, values_path: Path, out: Path) -> Path:
    schema = yaml.safe_load((template_dir / "schema.yaml").read_text())
    values = yaml.safe_load(values_path.read_text())
    return render_docx(template_dir / schema["template"]["file"], schema, values, out)


if __name__ == "__main__":
    try:
        print("rendered", render(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])))
    except DocMasterError as e:
        print(f"{e.data.get('code', e.code)}: {e}", *e.data.get("errors", []), sep="\n  "); sys.exit(2)
