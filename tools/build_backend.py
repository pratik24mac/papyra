"""Build the Python backend as a PyInstaller one-dir bundle and stage it, together with the
bundled templates, under apps/desktop/src-tauri/resources/ for Tauri to package.

    .venv/bin/python tools/build_backend.py            # macOS / Windows / Linux, current arch

One-dir starts in ~0.1 s and runs as a single process (one-file: 3.5 s and two processes).
"""
from __future__ import annotations
import os, platform, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "apps/desktop/src-tauri/resources"
NAME = "docmaster-backend"


def preflight() -> None:
    """Refuse to package an engine that would crash at runtime: every runtime module must import
    in the interpreter that runs PyInstaller (a stale venv is the usual cause)."""
    sys.path.insert(0, str(ROOT / "backend"))
    from docmaster.selfcheck import missing_modules
    missing = missing_modules()
    if missing:
        sys.exit(f"cannot build: missing runtime modules {missing}. Run: {sys.executable} -m pip install -r tools/requirements.txt")
    print("preflight: all runtime modules present")


def build_backend() -> Path:
    preflight()
    dist = ROOT / "backend/dist"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--console", "--name", NAME,
           "--paths", str(ROOT / "backend"), "--collect-data", "docx", "--collect-submodules", "keyring.backends",
           "--hidden-import", "keyring.backends.macOS", "--hidden-import", "keyring.backends.Windows", "--hidden-import", "psutil", "--exclude-module", "PIL", "--exclude-module", "tkinter",
           "--specpath", str(ROOT / "backend/pyinstaller"), "--workpath", str(ROOT / "backend/build"),
           "--distpath", str(dist), str(ROOT / "backend/entry.py")]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    out = dist / NAME
    exe = out / (NAME + (".exe" if os.name == "nt" else ""))
    assert exe.exists(), exe
    target = RES / "backend"
    if target.exists(): shutil.rmtree(target)
    shutil.copytree(out, target)
    if os.name != "nt":
        (target / NAME).chmod(0o755)
    return target


def stage_templates() -> Path:
    target = RES / "templates"
    if target.exists(): shutil.rmtree(target)
    keep = {"template.docx", "schema.yaml", "values.example.yaml", "values.example.json", "reference.pdf"}
    for schema in sorted((ROOT / "templates").glob("*/v*/schema.yaml")):
        src = schema.parent
        dst = target / src.parent.name / src.name
        dst.mkdir(parents=True)
        for f in src.iterdir():
            if f.name in keep:
                shutil.copy(f, dst / f.name)
    return target


if __name__ == "__main__":
    b = build_backend(); t = stage_templates()
    size = sum(f.stat().st_size for f in b.rglob("*") if f.is_file()) / 1e6
    print(f"backend: {b} ({size:.0f} MB, {platform.machine()})\ntemplates: {t} ({len(list(t.glob('*/v*')))} bundled)")
