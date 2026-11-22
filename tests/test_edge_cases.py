"""Negative, boundary and edge cases across the engine: validation limits, hostile input, odd but
valid input, RPC envelope abuse, filenames, job ids, dates, watermark config, batches."""
import json, sys
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from docmaster.docgen.render import validate, normalise_values, render_docx  # noqa: E402
from docmaster.docgen.dates import format_date, check_format  # noqa: E402
from docmaster.errors import ValidationError, TemplateInvalid, PdfConversionFailed  # noqa: E402
from docmaster.storage.paths import safe_stem, filename_from_pattern  # noqa: E402
from docmaster.storage.jobs import check_job_id, JobNotFound  # noqa: E402
from docmaster.pdfconv.watermark import config_from_schema  # noqa: E402
from docmaster.rpc.server import Server  # noqa: E402


def schema(*fields, group_id="g"):
    return {"template": {"id": "t", "version": 1, "name": "T", "file": "t.docx"}, "groups": [{"id": group_id, "label": "G", "fields": list(fields)}]}


def errors_of(sch, values):
    with pytest.raises(ValidationError) as e:
        validate(sch, values)
    return e.value.data["errors"]


# ---------------------------------------------------------------- required / empty / whitespace
def test_required_rejects_none_empty_and_whitespace_only_after_normalisation():
    sch = schema({"id": "name", "label": "N", "type": "text", "required": True})
    for bad in ({}, {"name": None}, {"name": ""}):
        assert errors_of(sch, bad) == ["name: required"]
    assert errors_of(sch, normalise_values(sch, {"name": "   "})) == ["name: required"]   # whitespace-only is empty
    validate(sch, {"name": "x"})                                                          # single character is enough


def test_optional_fields_accept_absent_none_and_empty():
    sch = schema({"id": "n", "label": "N", "type": "text"}, {"id": "d", "label": "D", "type": "date"}, {"id": "k", "label": "K", "type": "number"})
    validate(sch, {}); validate(sch, {"n": None, "d": "", "k": None})


# ---------------------------------------------------------------- length boundaries
def test_max_length_boundary_exact_and_plus_one():
    sch = schema({"id": "n", "label": "N", "type": "text", "validation": {"max_length": 5}})
    validate(sch, {"n": "abcde"})
    assert errors_of(sch, {"n": "abcdef"}) == ["n: longer than 5"]
    validate(sch, {"n": "héllo"})                                     # 5 characters, not bytes
    validate(sch, {"n": "日本語の五"})
    assert errors_of(sch, {"n": "a" * 100_000})[0].startswith("n: longer")   # huge input is rejected, not processed


def test_wrong_scalar_types_are_rejected_with_a_clear_message():
    sch = schema({"id": "n", "label": "N", "type": "text"}, {"id": "k", "label": "K", "type": "number"}, {"id": "c", "label": "C", "type": "checkbox"})
    assert errors_of(sch, {"n": 123}) == ["n: expected text"]
    assert errors_of(sch, {"n": ["a"]}) == ["n: expected text"]
    assert errors_of(sch, {"k": "12"}) == ["k: expected a number"]
    assert errors_of(sch, {"k": True}) == ["k: expected a number"]       # bool is not a number
    assert errors_of(sch, {"c": "yes"}) == ["c: expected true/false"]
    with pytest.raises(ValidationError): validate(sch, ["not", "an", "object"])


# ---------------------------------------------------------------- numbers
def test_number_boundaries_floats_and_extremes():
    sch = schema({"id": "k", "label": "K", "type": "number", "validation": {"min": 0, "max": 100}})
    validate(sch, {"k": 0}); validate(sch, {"k": 100}); validate(sch, {"k": 99.999})
    assert errors_of(sch, {"k": -0.001}) == ["k: less than 0"]
    assert errors_of(sch, {"k": 100.5}) == ["k: greater than 100"]
    assert errors_of(sch, {"k": float("inf")}) == ["k: greater than 100"]
    assert errors_of(sch, {"k": 10 ** 30}) == ["k: greater than 100"]


# ---------------------------------------------------------------- dates
@pytest.mark.parametrize("bad", ["2026-02-30", "2026-13-01", "2023-02-29", "2026-00-10", "2026-1-5", "12/03/2026", "2026-03-12T00:00", " 2026-03-12", "0000-01-01"])
def test_invalid_dates(bad):
    sch = schema({"id": "d", "label": "D", "type": "date"})
    msgs = errors_of(sch, {"d": bad}); assert len(msgs) == 1 and msgs[0].startswith("d:")


@pytest.mark.parametrize("good", ["2024-02-29", "2026-12-31", "1900-01-01", "9999-12-31"])
def test_valid_edge_dates(good):
    validate(schema({"id": "d", "label": "D", "type": "date"}), {"d": good})


def test_date_formatting_edges():
    assert format_date("2024-02-29", "Do MMMM YYYY") == "29th February 2024"
    assert format_date("2026-03-01", "Do") == "1st" and format_date("2026-03-02", "Do") == "2nd" and format_date("2026-03-03", "Do") == "3rd"
    assert format_date("2026-03-11", "Do") == "11th" and format_date("2026-03-12", "Do") == "12th" and format_date("2026-03-13", "Do") == "13th"
    assert format_date("2026-03-21", "Do") == "21st" and format_date("2026-03-22", "Do") == "22nd" and format_date("2026-03-23", "Do") == "23rd" and format_date("2026-03-31", "Do") == "31st"
    assert format_date("2026-03-05", "YY") == "26" and format_date("2000-01-01", "YY") == "00"
    assert format_date("2026-03-05", "no tokens here") == "no tokens here"
    with pytest.raises(ValueError): check_format("")
    with pytest.raises(ValueError): format_date("2026-02-30", "D MMMM YYYY")


# ---------------------------------------------------------------- select / email / url / pattern
def test_select_email_url_and_pattern_edges():
    sch = schema({"id": "s", "label": "S", "type": "select", "options": [{"value": "3", "label": "3 months"}, "6"]},
                 {"id": "e", "label": "E", "type": "email"}, {"id": "u", "label": "U", "type": "url"},
                 {"id": "p", "label": "P", "type": "text", "validation": {"pattern": r"^[A-Z]{3}-\d{4}$"}})
    validate(sch, {"s": "3"}); validate(sch, {"s": "6"})
    assert errors_of(sch, {"s": "3 months"})[0].startswith("s: must be one of")      # label is not a value
    assert errors_of(sch, {"s": 3})[0] == "s: expected text"
    for bad in ("plain", "a@b", "a b@c.de", "@c.de", "a@", "a@@b.co"):
        assert errors_of(sch, {"e": bad}) == ["e: not a valid email address"], bad
    validate(sch, {"e": "zoë@müller.example"}); validate(sch, {"e": "a+tag@b.co"})
    for bad in ("www.example.com", "ftp://x.y", "javascript:alert(1)", "http://", "https:// x.y"):
        assert errors_of(sch, {"u": bad}) == ["u: must start with http:// or https://"], bad
    validate(sch, {"u": "https://example.com/a?b=1#c"})
    validate(sch, {"p": "ABC-1234"})
    assert errors_of(sch, {"p": "abc-1234"})[0].startswith("p: does not match")


# ---------------------------------------------------------------- lists and groups
def test_list_boundaries_and_item_validation():
    sch = schema({"id": "entries", "label": "I", "type": "text_list", "required": True, "validation": {"min_items": 2, "max_items": 3}, "item": {"type": "text", "validation": {"max_length": 3}}},
                 {"id": "people", "label": "P", "type": "group_list", "item_fields": [{"id": "n", "label": "N", "type": "text", "required": True}, {"id": "age", "label": "A", "type": "number", "validation": {"min": 0}}]})
    assert errors_of(sch, {"entries": []}) == ["entries: at least one item required"]
    assert errors_of(sch, {"entries": ["a"]}) == ["entries: fewer than 2 items"]
    validate(sch, {"entries": ["a", "b"]}); validate(sch, {"entries": ["a", "b", "c"]})
    assert errors_of(sch, {"entries": ["a", "b", "c", "d"]}) == ["entries: more than 3 items"]
    assert errors_of(sch, {"entries": ["a", ""]}) == ["entries[1]: required"]              # empty item inside a list
    assert errors_of(sch, {"entries": ["a", "toolong"]}) == ["entries[1]: longer than 3"]
    assert errors_of(sch, {"entries": "a,b"}) == ["entries: expected a list"]
    assert errors_of(sch, {"entries": ["a", "b"], "people": ["not a dict"]}) == ["people[0]: expected an object"]
    assert errors_of(sch, {"entries": ["a", "b"], "people": [{"age": -1}]}) == ["people[0].n: required", "people[0].age: less than 0"]
    validate(sch, {"entries": ["a", "b"], "people": [{"n": "x", "extra_key": "ignored"}]})      # unknown keys are ignored


def test_all_errors_are_reported_at_once_and_in_schema_order():
    sch = schema({"id": "a", "label": "A", "type": "text", "required": True}, {"id": "b", "label": "B", "type": "number"}, {"id": "c", "label": "C", "type": "date"})
    assert errors_of(sch, {"b": "x", "c": "bad"}) == ["a: required", "b: expected a number", "c: expected a date as YYYY-MM-DD"]


# ---------------------------------------------------------------- schema abuse
def test_schema_rejects_reserved_ids_unknown_types_and_transforms():
    with pytest.raises(TemplateInvalid): validate(schema({"id": "items", "label": "x", "type": "text"}), {})
    with pytest.raises(TemplateInvalid): validate(schema({"id": "loop", "label": "x", "type": "text"}), {})
    with pytest.raises(TemplateInvalid): validate(schema({"id": "x", "label": "x", "type": "rating"}), {})
    with pytest.raises(TemplateInvalid): validate(schema({"id": "x", "label": "x", "type": "text", "transform": "shout"}), {})


# ---------------------------------------------------------------- transforms
def test_transform_upper_lower_title_and_where_it_applies():
    sch = schema({"id": "code", "label": "C", "type": "text", "transform": "upper"},
                 {"id": "mail", "label": "M", "type": "email", "transform": "lower"},
                 {"id": "name", "label": "N", "type": "text", "transform": "title"},
                 {"id": "num", "label": "K", "type": "number", "transform": "upper"},
                 {"id": "tags", "label": "T", "type": "text_list", "transform": "upper", "item": {"type": "text"}},
                 {"id": "people", "label": "P", "type": "group_list", "item_fields": [{"id": "n", "label": "N", "type": "text", "transform": "upper"}, {"id": "note", "label": "N", "type": "text"}]})
    out = normalise_values(sch, {"code": "  inv-0042 ", "mail": "Asha@Example.COM", "name": "asha verma-rao", "num": 5,
                                 "tags": ["alpha", "Beta"], "people": [{"n": "zoë", "note": "keep Me"}], "unknown": "dropped"})
    assert out["code"] == "INV-0042" and out["mail"] == "asha@example.com" and out["name"] == "Asha Verma-rao"
    assert out["num"] == 5 and out["tags"] == ["ALPHA", "BETA"] and out["people"] == [{"n": "ZOË", "note": "keep Me"}]
    assert "unknown" not in out
    assert normalise_values(sch, {"code": None})["code"] is None


def test_transform_reaches_the_document(tmp_path):
    from docx import Document
    d = Document(); d.add_paragraph("Ref {{ code }}"); src = tmp_path / "t.docx"; d.save(src)
    sch = schema({"id": "code", "label": "C", "type": "text", "transform": "upper", "required": True})
    out = render_docx(src, sch, normalise_values(sch, {"code": "inv-7"}), tmp_path / "o.docx")
    assert Document(out).paragraphs[0].text == "Ref INV-7"


# ---------------------------------------------------------------- filenames, job ids, paths
@pytest.mark.parametrize("raw,expected", [
    ("../../etc/passwd", "etc-passwd"), ("C:\\Windows\\x", "C-Windows-x"), ("a/b/c", "a-b-c"),
    ("   .hidden  ", "hidden"), ("", "document"), ("...", "document"), ("CON", "CON_"), ("lpt1", "lpt1_"),
    ("Zoë Müller", "Zoë Müller"), ("name" + chr(0) + "with" + chr(7) + "control", "name-with-control"), ("x" * 200, "x" * 80),
    ('a:b*c?d"e<f>g|h', "a-b-c-d-e-f-g-h"),
])
def test_safe_stem_neutralises_hostile_names(raw, expected):
    assert safe_stem(raw) == expected


def test_filename_pattern_edges():
    assert filename_from_pattern("{full_name}-{date}", {"full_name": "../x"}, __import__("datetime").date(2026, 3, 12)) == "x-2026-03-12"
    with pytest.raises(Exception): filename_from_pattern("{missing}", {})
    with pytest.raises(Exception): filename_from_pattern("{n}", {"n": ["lists", "are", "not", "usable"]})


@pytest.mark.parametrize("bad", ["", "../x", "a/b", "a\\b", "x" * 65, "-lead", "_lead", "sp ace", "job;rm", None, 42, "job\n"])
def test_job_ids_rejected(bad):
    with pytest.raises(JobNotFound):
        check_job_id(bad)


def test_job_ids_accepted():
    for ok in ("a", "A1", "x" * 64, "job-1_2", "0" * 10):
        assert check_job_id(ok) == ok


# ---------------------------------------------------------------- watermark config clamping
def test_watermark_config_clamps_out_of_range_values(tmp_path):
    (tmp_path / "w.png").write_bytes(b"x")
    cfg = config_from_schema({"template": {"watermark": {"image": "w.png", "opacity": -3, "scale": 9, "raster_width": 10, "rotation": "45", "position": "sideways", "invert": "maybe"}}}, tmp_path)
    assert cfg["opacity"] == 0.0 and cfg["scale"] == 1.0 and cfg["raster_width"] == 200 and cfg["rotation"] == 45.0 and cfg["invert"] == "auto"
    cfg = config_from_schema({"template": {"watermark": {"image": "w.png", "scale": 0.001, "raster_width": 99999}}}, tmp_path)
    assert cfg["scale"] == 0.05 and cfg["raster_width"] == 8000
    with pytest.raises(PdfConversionFailed): config_from_schema({"template": {"watermark": {"image": "../w.png"}}}, tmp_path)
    with pytest.raises(PdfConversionFailed): config_from_schema({"template": {"watermark": {"image": "/etc/passwd"}}}, tmp_path)


# ---------------------------------------------------------------- RPC envelope abuse
def test_rpc_envelope_edge_cases():
    sent = []
    class S(Server):
        def __init__(self): self.methods = {"echo": lambda ctx, **k: k, "noargs": lambda ctx: "ok"}
        def send(self, msg): sent.append(msg)
    s = S()
    s._handle({"id": 1, "method": "nope", "params": {}});               assert sent[-1]["error"]["code"] == -32601
    s._handle({"id": 2, "method": "echo", "params": [1, 2]});            assert sent[-1]["error"]["code"] == -32602
    s._handle({"id": 3, "method": "noargs", "params": {"extra": 1}});   assert sent[-1]["error"]["code"] == -32602     # unexpected parameter
    s._handle({"id": 4, "method": "echo", "params": {"a": "x" * 10_000}}); assert sent[-1]["result"] == {"a": "x" * 10_000}
    s._handle({"id": 0, "method": "noargs"});                           assert sent[-1]["result"] == "ok"               # id 0 is a valid id
    s._handle({"id": "str-id", "method": "noargs"});                    assert sent[-1]["id"] == "str-id"
    before = len(sent); s._handle({"method": "noargs"});                 assert len(sent) == before                       # notification: no reply
