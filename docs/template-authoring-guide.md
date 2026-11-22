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

## 3b. Dates, images and the last page
* **Dates** are entered with a picker and stored as `YYYY-MM-DD`; the document gets a formatted
  string. Format precedence: field `format` → template `date_format` → Settings → Dates →
  default `D MMMM YYYY` (12 March 2026). Tokens: `D` `DD` `Do` day, `M` `MM` `MMM` `MMMM`
  month, `YY` `YYYY` year, `ddd` `dddd` weekday. Ordinal suffixes (12th) are raised as superscript
  like Word does; `template.ordinal_superscript: false` keeps them inline. Inside the document a single tag can re-format:
  `{{ joining_date | date("DD/MM/YYYY") }}`.
* **Images** (logos, watermarks) are exported losslessly at their original resolution; use a
  PNG at the size you want printed (300 dpi or more for a full-page watermark).
* **Watermark**: do not rely on Word's own watermark; LibreOffice re-renders it (wrong size,
  washout lost, blurred). Put the image file in the template folder and declare it in the schema:
  ```yaml
  template:
    watermark:
      image: logo.svg        # in this template folder, or shared: templates/_assets/logo.svg (write `logo.svg` or `_assets/logo.svg`)
      grayscale: true        # drop colour (false keeps the original colours)
      black_white: false     # true: pure black and white instead of shades of gray
      remove_background: true  # white / near-white areas become transparent (default true)
      raster_width: 3000     # SVG only: pixels across; 3000 ≈ 300 dpi on an A4 page
      opacity: 0.15          # washout strength, 0..1 (Word's default is about 0.3)
      scale: 0.6             # width as a fraction of the page width
      rotation: 0            # degrees; 30–45 for a diagonal stamp
      position: center       # center | top | bottom
      pages: all             # all | first
  ```
  Papyra removes any Word watermark shape from the headers and stamps this image behind the
  text of every page in the PDF, losslessly, so it prints as sharp as the source file. Text above
  it stays searchable. An SVG is rendered through LibreOffice at `raster_width` pixels and
  cached. To see exactly what will be stamped before generating:
  ```bash
  .venv/bin/python tools/prepare_watermark.py logo.svg preview.png --grayscale
  ```
* **Extra last page**: empty paragraphs and page breaks at the very end of the document are
  removed automatically (`template.trim_trailing_blank: false` disables this). If the PDF still has
  one page more than Word shows, LibreOffice is reflowing text, almost always because a font
  used in the template is not installed on the machine converting it: use a common font or
  install the missing one.

## 4. Test-render and check the PDF
```bash
.venv/bin/python tools/lint_templates.py
.venv/bin/python tools/render_template.py templates/employment-contract/v1 templates/employment-contract/v1/values.example.yaml /tmp/test.docx
soffice --headless --convert-to pdf --outdir /tmp /tmp/test.docx     # or generate from the app
```
Compare the PDF with the original. When it is right, copy the PDF to
`templates/employment-contract/v1/reference.pdf`: the regression suite then guards it.

## 5. Use it in the app
Two places are scanned, and both work the same way (`<id>/v<n>/schema.yaml`):

| Where | Who uses it | How it appears |
|-------|-------------|----------------|
| `templates/` in the source tree | developers; bundled into the installer by the build | in dev runs and in every installed copy |
| **My templates folder**: `~/Documents/Papyra/templates` (shown in Settings → Diagnostics, with an Open button) | anyone with the installed app, no rebuild | immediately: click **Rescan templates** on the template screen, or just switch back to the app |

Copy the whole `<id>/v1/` folder into the templates folder. A template with a mistake does not
disappear: it is listed as **needs fixing** with the linter's findings, and "Open folder to fix"
takes you to it. A user template may not reuse a bundled template's id. Bump `v2` when you change
a template later; older documents keep pointing at the version they were made with.

## Sharing structure without content
```bash
.venv/bin/python tools/redact_docx.py ~/Private/contract.docx ~/Desktop/contract-structure.docx --strip-images
```
The redacted copy can be shared for help with tags, numbering or layout questions.
