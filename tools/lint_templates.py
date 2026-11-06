"""Lint every bundled template. Exit 1 on any error-level finding.  Usage: lint_templates.py [templates_dir]"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from docmaster.docgen.linter import lint_catalogue  # noqa: E402

results = lint_catalogue(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("templates"))
errors = 0
for name, findings in results.items():
    print(f"{name}: {'OK' if not findings else ''}")
    for x in findings:
        print("  ", x); errors += x.level == "error"
sys.exit(1 if errors else 0)
