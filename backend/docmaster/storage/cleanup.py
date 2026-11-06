"""Temporary-file hygiene: LibreOffice profiles are per-run temp dirs removed after each conversion;
this sweeps anything an interrupted run left behind, plus partial job files."""
from __future__ import annotations
import shutil, tempfile, time
from pathlib import Path


def sweep_temp(max_age_hours: float = 6.0) -> dict:
    root = Path(tempfile.gettempdir()); cutoff = time.time() - max_age_hours * 3600; removed = 0
    for d in root.glob("docmaster-lo-*"):
        try:
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True); removed += 1
        except OSError:
            pass
    return {"removed_temp_dirs": removed}


def sweep_output(output_dir: Path) -> dict:
    removed = 0
    if output_dir.exists():
        for p in output_dir.rglob("*.tmp"):
            try: p.unlink(); removed += 1
            except OSError: pass
    return {"removed_partial_files": removed}
