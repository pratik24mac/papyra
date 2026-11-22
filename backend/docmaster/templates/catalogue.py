"""Template catalogue: `<root>/<id>/v<n>/schema.yaml` under one or more roots.

* roots: the bundled templates shipped with the app and a user-writable folder, scanned together;
  the highest version of an id wins; a user template with the same id as a bundled one is reported
  as a problem rather than silently overriding it.
* rescan on every listing (cheap), so a folder dropped in while the app runs appears at once.
* lint on load: a template with a broken schema, missing file or linter error stays in the listing
  with `status: "error"` and its findings, instead of vanishing.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
import yaml
from ..errors import TemplateNotFound, TemplateInvalid

README = """Put your templates here, one folder per template:

  <template-id>/v1/template.docx          the tagged Word document
  <template-id>/v1/schema.yaml            the form definition
  <template-id>/v1/values.example.yaml    sample values for "Pre-fill with example values"
  _assets/logo.svg                        shared files (watermarks) any template can reference

Create the three files from a tagged Word document with:
  python tools/new_template.py <template-id> <tagged.docx> --name "Display name"
Then click "Rescan templates" in the app. A template with errors is shown in the app with
what to fix. See the authoring guide in the app (Help) or docs/template-authoring-guide.md.
"""


def normalise_yaml(obj):
    """Unquoted dates in YAML become `date` objects; the app wants ISO strings everywhere."""
    import datetime
    if isinstance(obj, dict):
        return {k: normalise_yaml(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalise_yaml(v) for v in obj]
    if isinstance(obj, datetime.datetime):
        return obj.date().isoformat()
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    return obj


@dataclass(frozen=True)
class Template:
    id: str
    version: int
    dir: Path
    schema: dict
    source: str = "bundled"              # bundled | user
    problems: tuple = ()                 # lint findings (strings); non-empty → unusable

    @property
    def docx(self) -> Path:
        return self.dir / self.schema["template"]["file"]

    @property
    def usable(self) -> bool:
        return not self.problems

    def summary(self) -> dict:
        t = self.schema.get("template", {})
        return {"id": self.id, "version": self.version, "name": t.get("name", self.id), "description": t.get("description", ""),
                "groups": self.schema.get("groups", []), "source": self.source, "dir": str(self.dir),
                "status": "ok" if self.usable else "error", "problems": list(self.problems),
                "has_examples": any((self.dir / n).exists() for n in ("values.example.yaml", "values.example.json"))}


@dataclass
class _Scan:
    templates: dict[str, Template] = field(default_factory=dict)
    signature: tuple = ()


class Catalogue:
    def __init__(self, root: Path, user_root: Path | None = None, lint: bool = True):
        self.root, self.user_root, self.lint = root, user_root, lint
        self._lint_cache: dict[tuple, tuple] = {}
        self._scan = _Scan()
        self.reload()

    # ---- scanning ----
    def _schema_paths(self) -> list[tuple[Path, str]]:
        out = []
        for source, root in (("bundled", self.root), ("user", self.user_root)):
            if root and root.exists():
                out += [(p, source) for p in sorted(root.glob("*/v*/schema.yaml"))]
        return out

    def _signature(self, paths) -> tuple:
        sig = []
        for p, _ in paths:
            try:
                docx_mtime = max((f.stat().st_mtime_ns for f in p.parent.glob("*.docx")), default=0)
                sig.append((str(p), p.stat().st_mtime_ns, docx_mtime))
            except OSError:
                sig.append((str(p), 0, 0))
        return tuple(sig)

    def _load_one(self, schema_path: Path, source: str) -> Template | None:
        m = re.fullmatch(r"v(\d+)", schema_path.parent.name)
        if not m or schema_path.parent.parent.name == "source":
            return None
        folder_id, folder_version = schema_path.parent.parent.name, int(m.group(1))
        problems: list[str] = []
        try:
            schema = normalise_yaml(yaml.safe_load(schema_path.read_text(encoding="utf8")) or {})
            if not isinstance(schema, dict) or "template" not in schema:
                raise ValueError("schema.yaml must have a top-level 'template' section")
            tid = str(schema["template"].get("id", folder_id)); version = int(schema["template"].get("version", folder_version))
            if version != folder_version or tid != folder_id:
                problems.append(f"folder '{folder_id}/v{folder_version}' and schema id/version '{tid}/v{version}' disagree")
        except Exception as e:  # noqa: BLE001
            schema = {"template": {"id": folder_id, "version": folder_version, "name": folder_id, "file": "template.docx"}, "groups": []}
            problems.append(f"schema.yaml cannot be read: {e}")
        t = Template(folder_id, folder_version, schema_path.parent, schema, source, tuple(problems))
        if not problems and not t.docx.exists():
            problems.append(f"{t.docx.name} is missing")
        if not problems and self.lint:
            key = (str(schema_path), self._signature([(schema_path, source)]))
            if key not in self._lint_cache:
                from ..docgen.linter import lint_template
                try:
                    findings = lint_template(t.docx, schema)
                    self._lint_cache[key] = tuple(str(f) for f in findings if f.level == "error")
                except Exception as e:  # noqa: BLE001
                    self._lint_cache[key] = (f"template cannot be opened: {e}",)
            problems += list(self._lint_cache[key])
        return Template(folder_id, folder_version, schema_path.parent, schema, source, tuple(problems))

    def reload(self, force: bool = False) -> bool:
        """Rescan the roots. Returns True when anything changed."""
        paths = self._schema_paths()
        sig = self._signature(paths)
        if not force and sig == self._scan.signature:
            return False
        found: dict[str, Template] = {}
        for schema_path, source in paths:
            t = self._load_one(schema_path, source)
            if t is None:
                continue
            if t.id in found and found[t.id].source != t.source:
                if t.source == "user":
                    clash = f"id '{t.id}' is already used by a bundled template; rename the folder"
                    found[f"{t.id} (user)"] = Template(f"{t.id} (user)", t.version, t.dir, t.schema, t.source, t.problems + (clash,))
                continue
            if t.id not in found or found[t.id].version < t.version:
                found[t.id] = t
        self._scan = _Scan(found, sig)
        return True

    # ---- queries ----
    def list(self, rescan: bool = True) -> list[dict]:
        if rescan:
            self.reload()
        return [t.summary() for t in sorted(self._scan.templates.values(), key=lambda t: (t.source != "bundled", t.id))]

    def get(self, template_id: str) -> Template:
        self.reload()
        t = self._scan.templates.get(template_id)
        if t is None:
            raise TemplateNotFound(data={"template_id": template_id})
        if not t.usable:
            raise TemplateInvalid(f"template '{template_id}' has errors: " + "; ".join(t.problems), data={"template_id": template_id, "problems": list(t.problems)})
        return t

    def example_values(self, template_id: str) -> dict:
        t = self.get(template_id)
        for name in ("values.example.yaml", "values.example.json"):
            p = t.dir / name
            if p.exists():
                return normalise_yaml(yaml.safe_load(p.read_text(encoding="utf8")) or {})
        return {}

    @staticmethod
    def ensure_user_root(path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        readme = path / "README.txt"
        if not readme.exists():
            readme.write_text(README, encoding="utf8")
        return path
