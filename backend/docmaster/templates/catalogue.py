"""Bundled template catalogue: templates/<id>/v<n>/schema.yaml. Highest version wins."""
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path
import yaml
from ..errors import TemplateNotFound, TemplateInvalid


@dataclass(frozen=True)
class Template:
    id: str
    version: int
    dir: Path
    schema: dict

    @property
    def docx(self) -> Path:
        return self.dir / self.schema["template"]["file"]

    def summary(self) -> dict:
        t = self.schema["template"]
        return {"id": self.id, "version": self.version, "name": t["name"], "description": t.get("description", ""),
                "groups": self.schema["groups"]}


class Catalogue:
    def __init__(self, root: Path):
        self.root = root
        self._templates: dict[str, Template] = {}
        self.reload()

    def reload(self) -> None:
        found: dict[str, Template] = {}
        for schema_path in sorted(self.root.glob("*/v*/schema.yaml")):
            m = re.fullmatch(r"v(\d+)", schema_path.parent.name)
            if not m or schema_path.parent.parent.name == "source":
                continue
            try:
                schema = yaml.safe_load(schema_path.read_text(encoding="utf8"))
                tid = schema["template"]["id"]; version = int(schema["template"]["version"])
            except Exception as e:  # noqa: BLE001
                raise TemplateInvalid(f"{schema_path}: {e}")
            if version != int(m.group(1)) or tid != schema_path.parent.parent.name:
                raise TemplateInvalid(f"{schema_path}: folder name and schema id/version disagree")
            t = Template(tid, version, schema_path.parent, schema)
            if not t.docx.exists():
                raise TemplateInvalid(f"{t.docx} is missing")
            if tid not in found or found[tid].version < version:
                found[tid] = t
        self._templates = found

    def list(self) -> list[dict]:
        return [t.summary() for t in sorted(self._templates.values(), key=lambda t: t.id)]

    def get(self, template_id: str) -> Template:
        try:
            return self._templates[template_id]
        except KeyError:
            raise TemplateNotFound(data={"template_id": template_id})
