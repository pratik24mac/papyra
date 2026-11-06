"""Persisted settings and the output-folder switch, exercised through the RPC method layer."""
import json, sys
from pathlib import Path
import pytest, yaml
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from docmaster.storage.settings import Settings, SettingInvalid  # noqa: E402
from docmaster.errors import OutputPathError  # noqa: E402
from docmaster.rpc.methods import build_methods  # noqa: E402


class Ctx:
    def progress(self, **k): pass


def test_settings_persist_and_validate(tmp_path):
    s = Settings(tmp_path / "data", tmp_path / "out-default")
    assert s.output_dir() == tmp_path / "out-default"
    new = tmp_path / "chosen"
    s.set("output_dir", str(new))
    assert s.output_dir() == new.resolve() and new.exists()
    assert Settings(tmp_path / "data", tmp_path / "out-default").output_dir() == new.resolve()   # survives restart
    s.set("output_dir", None)
    assert s.output_dir() == tmp_path / "out-default"
    with pytest.raises(SettingInvalid): s.set("output_dir", "relative/path")
    with pytest.raises(SettingInvalid): s.set("theme", "dark")
    with pytest.raises(SettingInvalid): s.set("output_dir", 42)
    (tmp_path / "data" / "settings.json").write_text("not json")
    assert Settings(tmp_path / "data", tmp_path / "out-default").output_dir() == tmp_path / "out-default"   # corrupt file → defaults


def test_unwritable_output_dir_is_rejected(tmp_path, monkeypatch):
    import docmaster.storage.settings as mod
    def refuse(path): raise OutputPathError(data={"path": str(path), "reason": "permission denied (simulated)"})
    monkeypatch.setattr(mod, "ensure_dir", refuse)
    s = Settings(tmp_path / "data", tmp_path / "out")
    with pytest.raises(OutputPathError):
        s.set("output_dir", str(tmp_path / "locked"))            # absolute on every OS
    assert s.output_dir() == tmp_path / "out"                      # nothing was stored


def test_generate_uses_the_chosen_output_dir(tmp_path):
    m = build_methods(ROOT / "templates", tmp_path / "default-out", data_dir=tmp_path / "data")
    assert m["settings.get"](Ctx())["output_dir"] == str(tmp_path / "default-out")
    chosen = tmp_path / "My Documents" / "Papyra"
    m["settings.set"](Ctx(), key="output_dir", value=str(chosen))
    assert m["system.diagnostics"](Ctx())["output_dir"] == str(chosen.resolve())
    values = yaml.safe_load((ROOT / "templates/resume-ats/v1/values.example.yaml").read_text())
    import shutil
    from docmaster.pdfconv.libreoffice import find_soffice
    if find_soffice() is None:
        pytest.skip("LibreOffice not installed")
    r = m["docgen.generate"](Ctx(), template_id="resume-ats", values=values, job_id="job-x")
    assert Path(r["docx_path"]).parent == chosen.resolve() / "job-x"
    assert m["jobs.get"](Ctx(), job_id="job-x")["output_dir"] == str(chosen.resolve())
    assert json.loads((chosen / "job-x" / "job.json").read_text())["job_id"] == "job-x"
