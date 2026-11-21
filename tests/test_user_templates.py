"""User templates folder: scanned with the bundled ones, rescanned without restart, broken ones
listed with their problems, id clashes reported, example values served per template."""
import shutil, sys
from pathlib import Path
import pytest, yaml
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from docmaster.templates.catalogue import Catalogue  # noqa: E402
from docmaster.errors import TemplateInvalid, TemplateNotFound  # noqa: E402
from docmaster.rpc.methods import build_methods  # noqa: E402
from docmaster.secrets.credential_store import CredentialStore  # noqa: E402

BUNDLED = ROOT / "templates"
SRC = BUNDLED / "resume-ats" / "v1"


class Ctx:
    def progress(self, **k): pass


class FakeKeyring:
    d: dict = {}
    def set_password(self, s, k, v): self.d[(s, k)] = v
    def get_password(self, s, k): return self.d.get((s, k))
    def delete_password(self, s, k): self.d.pop((s, k), None)


def copy_template(dst_root: Path, tid: str, name: str = "Copied"):
    d = dst_root / tid / "v1"; d.mkdir(parents=True)
    for f in ("template.docx", "schema.yaml", "values.example.yaml"):
        shutil.copy(SRC / f, d / f)
    schema = yaml.safe_load((d / "schema.yaml").read_text()); schema["template"]["id"] = tid; schema["template"]["name"] = name
    (d / "schema.yaml").write_text(yaml.safe_dump(schema, sort_keys=False, allow_unicode=True))
    return d


def test_user_folder_is_scanned_and_rescanned_without_restart(tmp_path):
    user = tmp_path / "user-templates"
    cat = Catalogue(BUNDLED, user)
    assert [t["id"] for t in cat.list()] == ["resume-ats"]
    copy_template(user, "offer-letter", "Offer letter")              # dropped in while "running"
    listing = cat.list()
    assert [(t["id"], t["source"], t["status"]) for t in listing] == [("resume-ats", "bundled", "ok"), ("offer-letter", "user", "ok")]
    assert cat.get("offer-letter").summary()["name"] == "Offer letter"
    assert cat.example_values("offer-letter")["full_name"]
    shutil.rmtree(user / "offer-letter")
    assert [t["id"] for t in cat.list()] == ["resume-ats"]           # removed folders disappear too
    assert cat.reload() is False                                     # nothing changed → no rescan work


def test_broken_user_template_is_listed_with_problems(tmp_path):
    user = tmp_path / "u"
    d = copy_template(user, "contract")
    (d / "template.docx").unlink()
    cat = Catalogue(BUNDLED, user)
    t = next(x for x in cat.list() if x["id"] == "contract")
    assert t["status"] == "error" and t["problems"] == ["template.docx is missing"]
    with pytest.raises(TemplateInvalid):
        cat.get("contract")
    shutil.copy(SRC / "template.docx", d / "template.docx")
    (d / "schema.yaml").write_text((d / "schema.yaml").read_text().replace("id: full_name", "id: full_name_typo", 1))
    t = next(x for x in cat.list() if x["id"] == "contract")
    assert t["status"] == "error" and any("M00" in p for p in t["problems"])   # linter mismatch surfaced
    (d / "schema.yaml").write_text("not: [valid")
    t = next(x for x in cat.list() if x["id"] == "contract")
    assert t["status"] == "error" and "cannot be read" in t["problems"][0] and t["name"] == "contract"


def test_user_template_cannot_shadow_a_bundled_id(tmp_path):
    user = tmp_path / "u"; copy_template(user, "resume-ats", "Impostor")
    cat = Catalogue(BUNDLED, user)
    listing = {t["id"]: t for t in cat.list()}
    assert listing["resume-ats"]["source"] == "bundled" and listing["resume-ats"]["status"] == "ok"
    clash = listing["resume-ats (user)"]
    assert clash["status"] == "error" and "already used by a bundled template" in clash["problems"][-1]


def test_methods_expose_rescan_and_example_values(tmp_path):
    user = tmp_path / "out" / "templates"
    m = build_methods(BUNDLED, tmp_path / "out", data_dir=tmp_path / "data", credentials=CredentialStore(backend=FakeKeyring()))
    assert (user / "README.txt").exists()                                       # folder created with instructions
    assert m["system.diagnostics"](Ctx())["user_templates_dir"] == str(user)
    assert m["templates.example_values"](Ctx(), template_id="resume-ats")["values"]["full_name"]
    with pytest.raises(TemplateNotFound):
        m["templates.example_values"](Ctx(), template_id="nope")
    copy_template(user, "nda", "NDA")
    r = m["templates.rescan"](Ctx())
    assert [t["id"] for t in r["templates"]] == ["resume-ats", "nda"]
