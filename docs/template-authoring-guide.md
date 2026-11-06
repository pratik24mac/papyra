# Template authoring guide (for confidential documents)

You can turn any Word document into a bundled template **without sharing it with anyone**:
every tool below runs locally in this repository, reads only the file you point it at, and the
app never uploads documents. If you want help with a document you cannot share, run
`tools/redact_docx.py` first: it keeps the exact structure (styles, numbering, tables, headers,
layout) but replaces every letter with `x` and every digit with `9`, so the structure can be
reviewed while the content stays private.

## 1. Tag the document in Word
Open a **copy** of the document and replace each value that changes per document with a tag:

| You want | Write in the document | Field type in schema |
|----------|----------------------|----------------------|
| a value | `{{ employee_name }}` | text / multiline / email / date / number / select / checkbox |
| a clickable link | `{{r website_link }}` (schema field `website_url`, type `url`) | url |
| a repeating paragraph (e.g. one per clause) | a paragraph containing only `{%p for c in clauses %}`, the paragraph to repeat with `{{ c }}`, then a paragraph with `{%p endfor %}` | text_list |
| a repeating group (e.g. one block per party) | `{%p for p in parties %}` … `{{ p.name }}`, `{{ p.address }}` … `{%p endfor %}` | group_list |
| repeating table rows | first cell of the row: `{%tr for r in rows %}`, last row: `{%tr endfor %}` | group_list |
| an optional section | `{%p if notes %}` … `{%p endif %}` | any optional field |

Rules that keep formatting intact:
* Type the tag **inside the run that has the formatting you want** (bold label, 12 pt, …); the value inherits it.
* Turn off Word's *AutoCorrect → "Straight quotes" with "smart quotes"* before typing tags, or paste tags as plain text. The linter rejects smart quotes next to tags (L001).
* A `{{r …}}` link tag must be the last thing in its run (T003).
* Field ids: lowercase, underscores, never `items`, `keys`, `values` (S002).
* Keep native Word numbering (Home → Multilevel list). Never type "1." by hand.
* Accept all tracked changes and delete comments (D001/D002).
* Leave page setup, headers/footers, fields (PAGE, NUMPAGES) as they are — they are preserved.

## 2. Scaffold the template folder
```bash
.venv/bin/python tools/new_template.py employment-contract ~/Private/contract-tagged.docx --name "Employment contract" --description "Standard contract for new hires"
```
This creates `templates/employment-contract/v1/` with `template.docx`, a `schema.yaml` skeleton
(one field per tag, types guessed from the names) and `values.example.yaml`, and runs the linter.

## 3. Edit `schema.yaml`
Set labels, `type`, `required`, `help`, `validation` (max_length, pattern, min/max, min/max_items),
`options` for selects, and move fields into sensible `groups`. For lists use `group_list` with
`item_fields`, or `text_list` with `item`. Set `output_filename`, `expected_pages` and
`essential_text` (fields whose values must appear in the PDF).

## 4. Test-render and check the PDF
```bash
.venv/bin/python tools/lint_templates.py
.venv/bin/python tools/render_template.py templates/employment-contract/v1 templates/employment-contract/v1/values.example.yaml /tmp/test.docx
soffice --headless --convert-to pdf --outdir /tmp /tmp/test.docx     # or generate from the app
```
Compare the PDF with the original. When it is right, copy the PDF to
`templates/employment-contract/v1/reference.pdf`: the regression suite then guards it.

## 5. Use it in the app
The catalogue picks up every `templates/<id>/v<n>/schema.yaml` automatically; restart the app and
the template appears on the template screen. Bump `v2` when you change a template later.

## Sharing structure without content
```bash
.venv/bin/python tools/redact_docx.py ~/Private/contract.docx ~/Desktop/contract-structure.docx --strip-images
```
The redacted copy can be shared for help with tags, numbering or layout questions.
