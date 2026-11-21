# Phase-1 tools

Developer tooling for authoring and verifying bundled templates. Nothing here ships to end users.

## Setup (macOS, Python 3.12)
```bash
python3.12 -m venv .venv && .venv/bin/pip install -r tools/requirements.txt
```
PDF checks need LibreOffice (`brew install --cask libreoffice`) and, for pixel diffs, poppler (`brew install poppler`).

## Commands
| Purpose | Command |
|---------|---------|
| Rebuild the resume template from the untouched source | `.venv/bin/python tools/build_resume_template.py` |
| Render a template with a values file | `.venv/bin/python tools/render_template.py templates/resume-ats/v1 templates/resume-ats/v1/values.example.yaml out.docx` |
| Structural diff of two .docx files | `.venv/bin/python tools/docx_structdiff.py a.docx b.docx` |
| Convert to PDF (isolated profile, as the app will) | `soffice --headless --norestore -env:UserInstallation=file:///tmp/lo-$$ --convert-to pdf --outdir out out.docx` |
| Run the tests | `.venv/bin/pytest -q` |
| Build the backend bundle + stage templates | `.venv/bin/python tools/build_backend.py` |
| Preview a watermark (SVG/PNG → processed PNG) | `.venv/bin/python tools/prepare_watermark.py logo.svg out.png --grayscale` |
| Regenerate license notices | `.venv/bin/python tools/licenses.py` |
| Sign the staged backend (macOS, Developer ID) | `tools/sign_backend_macos.sh "Developer ID Application: …"` |

## Template layout
```
templates/<id>/v<n>/template.docx        tagged Word file (built, never hand-edited)
templates/<id>/v<n>/schema.yaml          fields, validation, groups, output filename
templates/<id>/v<n>/values.example.yaml  sample values used by tests and the fidelity harness
templates/<id>/v<n>/reference.pdf        approved rendering (page count + text + pixels are compared against it)
templates/<id>/v<n>/samples/             example output for review
templates/source/                        original documents as received (read-only)
```

## Authoring rules learned in Phase 1
* Field ids must not shadow dict attributes (`items`, `keys`, `values`, …): Jinja resolves `s.items` as the method. The renderer rejects them.
* A `{{r …}}` (RichText/hyperlink) tag must be the last thing in its run; docxtpl re-opens the run without formatting after it.
* Space-after differences on the last item of a list are reproduced with `{%p if loop.last %}` / `{%p else %}` paragraph variants.
* Use `{%p set outer_last = loop.last %}` inside an outer loop to reach the outer loop state from a nested loop.
* Headings that introduce a list get `keep with next`.

## Backend and desktop app
See `apps/desktop/README.md` for the sidecar build, `npm run tauri dev`, and the automated self-test.
Backend unit tests live in `tests/test_backend_rpc.py`; run everything with `.venv/bin/pytest -q`.
