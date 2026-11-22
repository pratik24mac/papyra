"""Batch generation: several templates from one set of values into one folder per batch."""
import json, shutil, sys
from pathlib import Path
import pytest, yaml
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from docmaster.rpc.methods import build_methods  # noqa: E402
from docmaster.secrets.credential_store import CredentialStore  # noqa: E402
from docmaster.errors import ValidationError  # noqa: E402
from docmaster.pdfconv.libreoffice import find_soffice  # noqa: E402

SRC = ROOT / "templates" / "resume-ats" / "v1"
HAS_LO = find_soffice() is not None


class Ctx:
    def __init__(self): self.events = []
    def progress(self, **k): self.events.append(k)


class FakeKeyring:
    d: dict = {}
    def set_password(self, s, k, v): self.d[(s, k)] = v
    def get_password(self, s, k): return self.d.get((s, k))
    def delete_password(self, s, k): self.d.pop((s, k), None)


def second_template(user_root: Path, tid="cover-note", name="Cover note", **meta):
    d = user_root / tid / "v1"; d.mkdir(parents=True)
    for f in ("template.docx", "schema.yaml", "values.example.yaml"):
        shutil.copy(SRC / f, d / f)
    schema = yaml.safe_load((d / "schema.yaml").read_text()); schema["template"]["id"] = tid; schema["template"]["name"] = name
    schema["template"]["output_filename"] = "{full_name}-" + name.replace(" ", "-")
    schema["template"].update(meta)
    (d / "schema.yaml").write_text(yaml.safe_dump(schema, sort_keys=False, allow_unicode=True))
    return d


@pytest.fixture
def engine(tmp_path):
    user = tmp_path / "out" / "templates"; second_template(user)
    m = build_methods(ROOT / "templates", tmp_path / "out", data_dir=tmp_path / "data", credentials=CredentialStore(backend=FakeKeyring()), user_templates_dir=user)
    return m, tmp_path


@pytest.mark.skipif(not HAS_LO, reason="LibreOffice not installed")
def test_batch_generates_every_template_into_one_folder(engine):
    m, tmp = engine; ctx = Ctx()
    values = yaml.safe_load((SRC / "values.example.yaml").read_text())
    r = m["docgen.generate_batch"](ctx, templates=["resume-ats", "cover-note"], values=values, batch_id="batch-1")
    assert r["ok"] and r["person"] == values["full_name"] and [d["status"] for d in r["documents"]] == ["pdf_done", "pdf_done"]
    bdir = Path(r["batch_dir"])
    assert bdir.parent == tmp / "out" and bdir.name.startswith(values["full_name"].replace(" ", " ")[:5])
    files = sorted(p.name for p in bdir.iterdir() if p.is_file())
    assert "batch.json" in files and sum(f.endswith(".pdf") for f in files) == 2 and sum(f.endswith(".docx") for f in files) == 2
    assert len(list((bdir / ".jobs").glob("*.json"))) == 2
    # every document is a normal job: lookup, staleness, containment root
    for d in r["documents"]:
        info = m["jobs.get"](Ctx(), job_id=d["job_id"])
        assert not info["state"]["pdf_stale"] and info["output_dir"] == str(tmp / "out")
    b = m["batches.get"](Ctx(), batch_id="batch-1")
    assert [d["template_id"] for d in b["documents"]] == ["resume-ats", "cover-note"] and all(not d["state"]["pdf_stale"] for d in b["documents"])
    # progress carries the document position
    docs = [e for e in ctx.events if e.get("document")]
    assert {(e["index"], e["total"]) for e in docs} == {(0, 2), (1, 2)} and ctx.events[-1]["stage"] == "batch_done"
    # history: one row for the batch with both documents
    rows = m["history.list"](Ctx())["jobs"]
    assert len(rows) == 1 and rows[0]["kind"] == "batch" and len(rows[0]["documents"]) == 2 and rows[0]["pages"] == 4
    assert "Resume" in rows[0]["template_id"] and "Cover note" in rows[0]["template_id"]
    # one email with both PDFs
    e = m["email.prepare_eml"](Ctx(), job_ids=[d["job_id"] for d in r["documents"]], message={"to": "a@b.co", "subject": "Docs", "body": "Hi"})
    assert len(e["attachments"]) == 2 and Path(e["eml_path"]).exists() and "(+1 more)" in e["eml_path"]
    # a second batch for the same person on the same day gets its own folder
    r2 = m["docgen.generate_batch"](Ctx(), templates=["resume-ats"], values=values, batch_id="batch-2")
    assert Path(r2["batch_dir"]) != bdir and Path(r2["batch_dir"]).name.endswith("(2)")
    # delete the batch: rows and folder gone
    assert m["history.delete_batch"](Ctx(), batch_id="batch-1", delete_files=True) == {"batch_id": "batch-1", "removed_rows": 2, "removed_files": True}
    assert not bdir.exists() and len(m["history.list"](Ctx())["jobs"]) == 1


@pytest.mark.skipif(not HAS_LO, reason="LibreOffice not installed")
def test_one_failing_document_does_not_stop_the_batch(tmp_path):
    user = tmp_path / "out" / "templates"; second_template(user, "strict-note", "Strict note", expected_pages={"min": 9, "max": 9})
    m = build_methods(ROOT / "templates", tmp_path / "out", data_dir=tmp_path / "data", credentials=CredentialStore(backend=FakeKeyring()), user_templates_dir=user)
    values = yaml.safe_load((SRC / "values.example.yaml").read_text())
    r = m["docgen.generate_batch"](Ctx(), templates=["strict-note", "resume-ats"], values=values, batch_id="b")
    assert not r["ok"]
    assert [d["status"] for d in r["documents"]] == ["failed", "pdf_done"]
    assert r["documents"][0]["error"]["code"] == "PDF_INVALID" and r["documents"][0]["docx_path"]      # Word file kept
    assert m["history.list"](Ctx())["jobs"][0]["status"] == "pdf_failed"


def test_batch_validation_names_the_template_and_overrides_apply(tmp_path):
    user = tmp_path / "out" / "templates"; second_template(user)
    m = build_methods(ROOT / "templates", tmp_path / "out", data_dir=tmp_path / "data", credentials=CredentialStore(backend=FakeKeyring()), user_templates_dir=user)
    with pytest.raises(ValidationError) as e:
        m["docgen.generate_batch"](Ctx(), templates=["resume-ats", "cover-note"], values={})
    assert e.value.data["template_id"] == "resume-ats"
    with pytest.raises(ValidationError):
        m["docgen.generate_batch"](Ctx(), templates=[], values={})
    if not HAS_LO: pytest.skip("LibreOffice not installed")
    values = yaml.safe_load((SRC / "values.example.yaml").read_text())
    r = m["docgen.generate_batch"](Ctx(), templates=["resume-ats", "cover-note"], values=values,
                                   values_by_template={"cover-note": {"full_name": "Override Person"}}, batch_id="ov")
    names = {d["template_id"]: Path(d["docx_path"]).name for d in r["documents"]}
    assert names["cover-note"].startswith("Override Person") and names["resume-ats"].startswith(values["full_name"])
    assert r["person"] == values["full_name"]                                              # folder named from the shared values
