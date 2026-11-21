"""Unit tests for the stdio JSON-RPC server, safe paths and the template catalogue (no LibreOffice needed)."""
import io, json, sys, threading
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from docmaster.rpc.server import Server  # noqa: E402
from docmaster.errors import ValidationError, OutputPathError, TemplateInvalid  # noqa: E402
from docmaster.storage.paths import safe_stem, filename_from_pattern, unique_path  # noqa: E402
from docmaster.templates.catalogue import Catalogue  # noqa: E402


def run_server(lines, methods):
    out = io.StringIO()
    Server(methods, inp=io.StringIO("\n".join(lines) + "\n"), out=out, workers=2).serve_forever()
    return [json.loads(l) for l in out.getvalue().splitlines()]


def req(i, method, params=None):
    return json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params or {}})


def test_request_response_and_errors():
    methods = {"echo": lambda ctx, **p: p, "boom": lambda ctx: 1 / 0,
               "bad": lambda ctx: (_ for _ in ()).throw(ValidationError(data={"errors": ["x: required"]}))}
    msgs = run_server([req(1, "echo", {"a": 1}), req(2, "nope"), "not json", json.dumps({"jsonrpc": "2.0", "id": 3, "method": 5}),
                       req(4, "echo", {"zzz": 1, "a": 2}), req(5, "boom"), req(6, "bad"), req(7, "system.shutdown")],
                      methods | {"system.shutdown": lambda ctx: {"ok": True}})
    by_id = {m.get("id"): m for m in msgs}
    assert by_id[1]["result"] == {"a": 1}
    assert by_id[2]["error"]["code"] == -32601
    assert any(m.get("error", {}).get("code") == -32700 for m in msgs)          # parse error
    assert by_id[3]["error"]["code"] == -32600                                   # invalid request
    assert by_id[4]["result"] == {"zzz": 1, "a": 2}
    assert by_id[5]["error"]["code"] == -32000 and by_id[5]["error"]["data"]["type"] == "ZeroDivisionError"
    assert by_id[6]["error"]["data"] == {"code": "VALIDATION_ERROR", "errors": ["x: required"]}
    assert by_id[7]["result"] == {"ok": True}


def test_invalid_params_is_32602():
    msgs = run_server([req(1, "needs", {"wrong": 1})], {"needs": lambda ctx, right: right})
    assert msgs[0]["error"]["code"] == -32602


def test_progress_notifications_precede_result():
    def work(ctx):
        ctx.progress(job_id="j", stage="a"); ctx.progress(job_id="j", stage="b"); return {"done": True}
    msgs = run_server([req(1, "work")], {"work": work})
    assert [m.get("method") for m in msgs[:2]] == ["job.progress", "job.progress"]
    assert msgs[2]["result"] == {"done": True}


def test_slow_call_does_not_block_ping():
    gate = threading.Event()
    def slow(ctx): gate.wait(5); return "slow"
    out = io.StringIO()
    server = Server({"slow": slow, "ping": lambda ctx: "pong"}, inp=io.StringIO(req(1, "slow") + "\n" + req(2, "ping") + "\n"), out=out, workers=2)
    t = threading.Thread(target=server.serve_forever); t.start()
    for _ in range(200):
        if '"pong"' in out.getvalue(): break
        threading.Event().wait(0.01)
    assert '"pong"' in out.getvalue() and '"slow"' not in out.getvalue()
    gate.set(); t.join(5)
    assert '"slow"' in out.getvalue()


def test_unicode_round_trip():
    msgs = run_server([req(1, "echo", {"n": "Zoë Müller-Łukasz ☐"})], {"echo": lambda ctx, **p: p})
    assert msgs[0]["result"]["n"] == "Zoë Müller-Łukasz ☐"


def test_safe_filenames(tmp_path):
    assert safe_stem("../../etc/passwd") == "etc-passwd"
    assert safe_stem("CON") == "CON_"
    assert safe_stem("  Name: with / slashes \\ and *stars*  ") == "Name-with-slashes-and-stars"
    assert safe_stem("x" * 200) == "x" * 80
    assert filename_from_pattern("{full_name}-Resume-{date}", {"full_name": "Zoë / Pandey"}).startswith("Zoë-Pandey-Resume-20")
    with pytest.raises(OutputPathError):
        filename_from_pattern("{missing}", {})
    (tmp_path / "a.docx").write_text("x")
    assert unique_path(tmp_path, "a", ".docx").name == "a (2).docx"


def test_catalogue_lists_bundled_templates():
    cat = Catalogue(ROOT / "templates")
    ids = [t["id"] for t in cat.list()]
    assert ids == ["resume-ats"]
    t = cat.get("resume-ats")
    assert t.version == 1 and t.docx.exists() and t.summary()["name"] == "Resume (ATS-friendly)"


def test_catalogue_reports_inconsistent_folder_instead_of_hiding_it(tmp_path):
    d = tmp_path / "foo" / "v1"; d.mkdir(parents=True)
    (d / "schema.yaml").write_text("template: {id: bar, version: 1, file: t.docx}\ngroups: []\n")
    cat = Catalogue(tmp_path)
    [t] = cat.list()
    assert t["id"] == "foo" and t["status"] == "error" and "disagree" in t["problems"][0]
    with pytest.raises(TemplateInvalid):
        cat.get("foo")


def test_validate_extended_field_types():
    from docmaster.docgen.render import validate
    schema = {"groups": [{"id": "g", "label": "G", "fields": [
        {"id": "d", "label": "Date", "type": "date", "required": True},
        {"id": "n", "label": "Num", "type": "number", "validation": {"min": 1, "max": 10}},
        {"id": "s", "label": "Sel", "type": "select", "options": [{"value": "a", "label": "A"}, "b"]},
        {"id": "c", "label": "Chk", "type": "checkbox"},
    ]}]}
    validate(schema, {"d": "2026-11-03", "n": 5, "s": "b", "c": False})
    with pytest.raises(ValidationError) as e:
        validate(schema, {"d": "2026-02-30", "n": 11, "s": "zzz", "c": "yes"})
    errs = e.value.data["errors"]
    assert any("d: not a real date" in x for x in errs) and any("n: greater than 10" in x for x in errs)
    assert any("s: must be one of" in x for x in errs) and any("c: expected true/false" in x for x in errs)
    with pytest.raises(ValidationError) as e:
        validate(schema, {"d": "3 Nov 2026", "n": "5"})
    assert any("YYYY-MM-DD" in x for x in e.value.data["errors"]) and any("n: expected a number" in x for x in e.value.data["errors"])
    with pytest.raises(TemplateInvalid):
        validate({"groups": [{"id": "g", "label": "G", "fields": [{"id": "x", "label": "X", "type": "rating"}]}]}, {})
