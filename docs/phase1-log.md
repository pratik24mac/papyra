# Phase 1 log — feasibility results

## 2026-11-03 — Resume template end-to-end on macOS
Environment: macOS 26.3 (Apple Silicon), Python 3.12.15, python-docx 1.2.0, docxtpl 0.20.2,
LibreOffice 26.8.2.2 (installed via Homebrew this session), poppler 26.10 (dev only).

**Built**: `templates/resume-ats/v1/` (template.docx, schema.yaml, values.example.yaml, samples/),
`tools/` (build, render, structural diff), `tests/test_resume_template.py`.

**Result**: rendering the example values through the template and LibreOffice reproduces the
source resume. Measured against the source converted by the same LibreOffice:

| Check | Result |
|-------|--------|
| Structural diff (paragraph props, run formatting, numbering, sections) | Only the four intended changes differ |
| PDF page count | 2 = 2 |
| PDF text lines per page | 45/45 and 38/38; differing lines are only the title/date separation introduced by fix 1 |
| Pixel diff page 1 (100 dpi) | 0.19 % (right-aligned dates) |
| Pixel diff page 2 | 16 % — the whole page shifted up by the two removed blank lines; content identical |
| Hyperlinks | Recreated as relationships, blue + underline preserved |

Review images: `docs/templates/resume-ats-review/page1-source-vs-generated.png`, `page2-…png`.
**Approved 2026-11-03** → `templates/resume-ats/v1/reference.pdf`; `tests/test_resume_template.py::test_matches_approved_reference`
now fails if page count, text or more than 0.5 % of pixels per page drift from it.

**Changes vs the source** (all deliberate): tab between title and dates; two blank paragraphs removed;
Google round-trip part removed and document properties set; job titles keep-with-next (added after
the first run showed a title orphaned at the bottom of page 1).

**Findings that change the design**
1. Jinja resolves `item.items` as the dict method → field ids must never shadow dict attributes.
   The renderer now rejects reserved ids; this rule goes into the schema validator and the template linter.
2. docxtpl re-opens a run **without** its formatting after a `{{r }}` tag → a RichText/hyperlink tag
   must end its run. The linter will flag text following `{{r }}` inside a run.
3. The schema needs `group_list` and `text_list` field types (repeating groups); the form engine
   must support nested repeaters (jobs → bullets).
4. Spacing of the last item in a list is paragraph-level, so the template needs `loop.last`
   paragraph variants; the build script generates them.
5. LibreOffice conversion time: 0.9–2.3 s per document with a fresh isolated profile.

**Still open**: the same pipeline on Windows; Word-rendered comparison (no Word here);
the Rust ↔ Python sidecar PoC; the second document's field model (awaiting your answer).

## 2026-11-03 — Tauri ↔ Python sidecar proof of concept (macOS)
Environment: Rust 1.99.1 (rustup via Homebrew), Tauri 2 + tauri-plugin-shell 2, Node 24, PyInstaller 6.22.

**Built**: `backend/` (package `docmaster`: stdio JSON-RPC server, catalogue, docgen, LibreOffice
converter, error taxonomy, safe paths), `apps/desktop/` (Tauri 2 shell: sidecar supervisor and RPC
client in Rust, allow-listed `backend_call` command, PoC React page, automated self-test),
`tests/test_backend_rpc.py` (8 tests; 16 total, all passing).

**Self-test through the real Tauri app** (`DOCMASTER_SELFTEST=1 ./doc-master`), three runs:

| Step | Result | Time |
|------|--------|------|
| ping (process spawn → first reply) | PASS | 20.9 s on the very first launch of a new binary, then 3.5 s |
| diagnostics (LibreOffice 26.8.2.2 found, output dir writable) | PASS | 0.2 s |
| templates.list | PASS | < 1 ms |
| generate with invalid values → `VALIDATION_ERROR` with field list | PASS | < 1 ms |
| generate example resume → DOCX + PDF, 2 pages | PASS | 0.97 s |
| progress notifications forwarded as Tauri events | 5 received | — |
| ping during a running conversion (python client) | answered | 1 ms |
| graceful shutdown (`system.shutdown`, then kill) | backend logs "rpc server stopped" | — |

**Decisions confirmed**
* JSON-RPC over stdio driven by Rust works with no HTTP server; the WebView only sees
  `backend_call` (allow-list; `system.shutdown` is not callable from the UI) and `example_values`.
* Validation happens before anything touches the disk; a failed PDF leaves the DOCX in place.

**Findings that change the plan**
1. **PyInstaller one-file is too slow**: 3.5 s cold start on every launch (it unpacks 19 MB to a temp
   dir). One-dir starts in **98 ms**. → The product bundles the one-dir folder (41 MB) as a Tauri
   resource and spawns it with `shell().command()`; Tauri's `sidecar()`/externalBin (single file)
   is kept only for this PoC.
2. **macOS first-launch scan**: the first execution of any new unsigned binary costs ~20 s
   (Gatekeeper/XProtect), paid once per binary version. Signing + notarisation is required for
   release builds regardless; the app must show a "preparing backend" state on first start.
3. Non-ASCII letters must be allowed in output filenames (Zoë, Müller); fixed in `storage/paths.py`.
4. The essential-text PDF check must be case/whitespace-insensitive (templates upper-case names).

**Not covered by automation**: the WebView → Rust `invoke` path and the PoC page were not clicked
by a script (Tauri's WebDriver has no macOS support); run `npm run tauri dev` in `apps/desktop` to
try the buttons. Windows build/run of the same chain is still pending.

## 2026-11-03 — Phase 2: desktop foundation
**Built**
* `apps/desktop/src/` — Ant Design 6 shell: Dashboard, New-document wizard (Template → Details →
  Review → Generate), Settings/Diagnostics; engine status badge driven by `backend://status` events.
* Metadata-driven form (`components/FieldRenderer.tsx`): text, multiline, email, url, date, number,
  select, checkbox, plus `group_list` (nested repeating groups) and `text_list`; rules derived from
  the schema (`lib/schema.ts`), values preserved across steps in a store, server-side validation
  errors mapped back onto fields, defaults with `{field}` placeholders expanded.
* Typed API layer (`api/backend.ts`, `api/types.ts`) with a **browser mock mode** (no Tauri) so
  screens can be developed and screenshot-tested; error codes → user actions in `lib/errors.ts`.
* Rust supervisor: `Starting → Ready → Restarting (≤3) → Failed` lifecycle, crash restart verified
  by killing the backend under a running app (ready again in 6 s, no orphan processes),
  `backend_status` command.
* Python validator: date, number, select, checkbox types; unknown types rejected.
* Tests: 19 pytest (incl. `test_contract.py`, which checks the RPC method list and error codes agree
  across Python, Rust and TypeScript), 7 Vitest; Tauri self-test still PASS.

**Verified in the browser (mock mode)**: dashboard → template card (17 inputs, 11 required) →
form with nested positions/highlights → example values fill all 84 inputs → review → generation
progress with per-stage messages → result; PDF-failure path shows the kept Word path and an action.

**Findings**
1. Ant Design `Form.Item` injects `value/onChange/id` into its direct child: a wrapper component must
   forward them (first run rendered every scalar input empty).
2. Killing only the PyInstaller one-file *bootloader* leaves the Python child alive holding the pipes,
   so no termination is observed — a second reason to ship one-dir (single process).
3. antd 6 renamed `direction` → `orientation` and `Steps.items.description` → `content`.

**Exit criterion met**: pick template → fill form → review → generate, offline, with backend health
shown. Not done in this phase: output-folder setting persistence (Phase 5), PDF preview (Phase 3),
the Windows build.

## 2026-11-03 — Phase 3: document generation
**Built**
* `storage/jobs.py`: one `job.json` per job (paths, SHA-256 of DOCX and PDF, which DOCX the PDF was
  made from). No form values are stored. `jobs.get` reports `pdf_stale` when the DOCX changed,
  or the PDF is missing/modified; `docgen.convert_pdf` rebuilds the PDF from the current DOCX.
* `docgen/linter.py` + `tools/lint_templates.py`: schema sanity (duplicate/reserved ids, unknown
  types), document hygiene (tracked changes, comments, dangling numbering ids, leftover customXML),
  tag syntax (unbalanced tags, smart quotes, text after `{{r }}`), template ↔ schema agreement.
  Bundled templates are linted in CI (`tests/test_jobs_and_linter.py`).
* `docgen/ooxml.py`: numbering restart (`w:num` + `lvlOverride/startOverride`), complex fields
  (PAGE/NUMPAGES), `updateFields`, document properties, tracked-change/comment detection.
  Generated documents now carry title/author/subject properties.
* Rust `files.rs`: `read_job_pdf` (bytes to the WebView), `open_job_file`, `reveal_job_folder`,
  `save_job_copy` (native save dialog). The WebView names a job, never a path; Rust resolves the
  path through the backend and rejects anything outside the output folder or a stale PDF.
* Frontend: step 5 "Preview" with pdf.js (`components/PdfViewer.tsx`), open/save/reveal actions,
  a stale banner with "Regenerate PDF", re-check on window focus; CSP extended for the pdf.js
  worker. "Continue to email" is present but disabled until Phase 4.

**Verified**
* Tauri self-test (real sidecar): generate → `jobs.get` fresh → append a byte to the DOCX →
  `jobs.get` reports `docx_changed` and `pdf_stale` → `convert_pdf` (0.9 s) → fresh again;
  path resolution inside the output dir passes and `../etc` is rejected. 7 progress events.
* Browser mock: two pages rendered by pdf.js; stale banner hides the preview and disables
  Open PDF / Save a copy; Regenerate restores the preview.
* 26 pytest, 7 Vitest.

**Decisions**
* PDF re-conversion after an external edit validates page count only: the text may legitimately
  differ from the form values, and the job record deliberately holds no form values.
* Fidelity is gated by `test_matches_approved_reference` (page count, text, ≤0.5 % pixels).

**Exit criterion**: DOCX + PDF for every bundled template with the regression suite green — met for
the one bundled template; the second template still awaits your choice of field model.

## 2026-11-03 — Sign-in, dark iCloud-style UI, template-authoring kit
* **Sign-in** (`src-tauri/src/auth.rs`): fixed credentials, verified in Rust against a salted SHA-256
  digest with constant-time comparison and a growing delay after failures. `backend_call`,
  `example_values` and every file command require a signed-in session, so the WebView cannot reach
  the backend or generated files before login. Default `admin` / `DocMaster!2026`; change with
  `tools/set_password.py <user> <password>` and rebuild. Unit test in `cargo test`.
* **UI**: always dark, iCloud-like (glass surfaces, tiles, SF typography, pill buttons, top bar with
  segmented navigation and an avatar menu with Sign out). Login screen is a centred glass card.
* **Authoring kit for confidential documents** (`docs/template-authoring-guide.md`):
  `tools/new_template.py` scaffolds `templates/<id>/v1/` (template, schema skeleton with guessed
  types, example values) from a Word file you tagged yourself and lints it;
  `tools/redact_docx.py` writes a structure-only copy (letters → x, digits → 9, tags/styles/
  numbering/tables kept, properties cleared, optional image stripping) that is safe to share.
  Linter/renderer fix: a url field counts as used when only its `{{r x_link }}` tag appears.
* Tests: 29 pytest, 7 Vitest, 1 cargo test.

## 2026-11-03 — Papyra: name, icon, configurable output folder
* **Name**: "Doc Master" → **Papyra** (approved). Product name, bundle identifier
  `com.papyra.desktop`, window title, binary `papyra`, UI strings, default output folder
  `~/Documents/Papyra`. Internal identifiers (`docmaster` Python package, sidecar binary name) are
  unchanged on purpose; the working folder keeps its old name.
* **Icon**: `design/papyra-icon-1024.png` (papyrus scroll on an indigo→blue gradient, drawn with
  Pillow at 4× and downsampled); `tauri icon` generated the macOS `.icns`, Windows `.ico` and PNG
  sizes in `src-tauri/icons/`; the same mark is used on the login card and in the top bar.
* **Output folder** (approved: picker in Settings): `storage/settings.py` persists
  `settings.json` in the app data dir (Rust passes `--data-dir` = Tauri `app_data_dir`).
  `settings.get` / `settings.set` RPC; the backend reads the current folder on every call, so a
  change applies immediately with no restart; unwritable or relative paths are rejected. Rust
  `choose_output_dir` opens the native folder picker; file-path containment is now checked against
  the folder the backend reports, not the start-up default. Reset-to-default removes the override.
* Self-test: `settings.set` → generate lands in the chosen folder → reset. Tests: 32 pytest.

## 2026-11-03 — Phase 4: email drafts (offline .eml + IMAP for Porkbun)
Decision (approved): the user's mailbox is Porkbun hosted email, a standard IMAP/SMTP account, so
Gmail API and Microsoft Graph are **dropped**. Drafts are saved over IMAP (works for any provider).

**Built**
* `email/mime.py`: one `EmailMessage` builder for both workflows (RFC 5322/2047/2231, UTF-8 body,
  base64 PDF, `Message-ID`, `X-Unsent: 1` for .eml); recipient parsing accepts lists, `Name <addr>`,
  comma/semicolon separators and international addresses; 25 MB attachment limit.
* `email/eml.py`: writes next to the PDF (never overwrites), re-parses the file and checks the
  attachment bytes round-trip before reporting success.
* `email/imap_draft.py`: IMAP4 over TLS, LOGIN, Drafts folder found via the RFC 6154 `\Drafts`
  special-use flag with name fallbacks, `APPEND` with `\Draft \Seen`, success only on `OK`
  (APPENDUID parsed when offered). Errors map to EMAIL_AUTH_FAILED / EMAIL_NETWORK_ERROR /
  EMAIL_IMAP_ERROR. Nothing is ever sent.
* `secrets/credential_store.py`: `keyring` (macOS Keychain / Windows Credential Manager) with
  1000-char chunking for Windows' 2560-byte limit. The password never touches settings.json,
  job.json or logs; the account (email, host, port, folder) lives in settings.json.
* RPC: `email.prepare_eml`, `email.create_imap_draft`, `email.imap_get_account`, `email.imap_test`,
  `email.imap_save_account` (verifies the login before storing anything), `email.imap_remove_account`.
  Both draft workflows refuse a stale PDF (`PDF_STALE`). Drafts are recorded in `job.json`.
* UI: step 6 "Email" (attachment card, To/CC/BCC/Subject/Body prefilled from the template's
  email group, workflow choice, confirmation dialog, results with Open/Show in folder);
  Settings → "Email account" card (Porkbun defaults `imap.porkbun.com:993`, Test connection,
  Connect, Disconnect).
* Rust: email methods allow-listed (90 s timeout), `eml` file kind for open/reveal.
* PyInstaller: `keyring.backends` collected so the frozen sidecar can use the Keychain.

**Verified**: 39 pytest (fake IMAP server covers folder detection, auth/network/IMAP errors,
APPEND payload, chunked credentials, end-to-end methods); self-test through the frozen sidecar
creates a .eml, rejects a bad address and reports no account.
**Real-server check (2026-11-03)**: the user connected a Porkbun mailbox in Settings and the
draft with the PDF attached appeared in the mailbox's Drafts folder. Phase 4 exit criterion met.

**Known client behaviour for .eml**: Outlook opens it as an editable unsent message
(`X-Unsent`); Apple Mail and Thunderbird open it as a received message to forward. The IMAP
draft is the reliable path.

## 2026-11-03 — Phase 5: persistence, privacy, VPN
* **History** (`storage/history.py`): SQLite in the app data dir, metadata only (template, time,
  paths, pages, draft outcomes). Dashboard "Recent documents" with Open (resumes preview/email),
  Show in folder, Delete (row only, or with files). `history.clear` deletes everything.
  `keep_history` toggle turns recording off.
* **Logs** (`logging_.py`): stderr + rotating file in `data/logs`, redacting emails, secrets and long
  digit runs before writing; RPC params are never logged.
* **Network policy** (`net.py`): `offline_mode` setting enforced in the backend before any IMAP
  connection; `network.check` runs DNS → TCP → TLS to the mail host without credentials, so VPN or
  DNS problems are visible per stage. Privacy screen lists every possible outbound destination.
* **Cleanup** (`storage/cleanup.py`): startup sweep of leftover LibreOffice temp profiles; on-demand
  removal of partial files; clear logs.
* **Privacy screen** (Settings → Privacy & network): what is stored where with sizes, what is
  never stored, telemetry = none, offline mode, history toggle, delete-all, clear logs/temp,
  VPN reachability test, open data folder.
* `docs/security-review.md`: IPC surface, auth, secrets, data at rest, network, known gaps.
* Tests: 46 pytest incl. the **offline acceptance test** (socket creation disabled → generation,
  PDF, .eml, history all pass) and offline-mode enforcement; self-test covers history list/delete,
  privacy summary and offline blocking through the frozen sidecar.

## 2026-11-06 — Phase 6: testing and distribution (macOS)
* **Backend packaging switched to one-dir** (`tools/build_backend.py`): PyInstaller one-dir bundle
  (56 MB, Pillow/tkinter excluded) staged with the templates under `src-tauri/resources/` and shipped
  as Tauri resources. The Rust supervisor resolves the executable from the app resources (dev tree
  and `DOCMASTER_BACKEND` as fallbacks; the one-file sidecar is no longer used). Result: engine ready
  in **0.17–0.24 s** instead of 3.5 s, single process, clean termination.
* **macOS bundle**: `npm run tauri build -- --bundles app` → `Papyra.app` (68 MB); DMG via
  `tools/make_dmg_macos.sh` (hdiutil; Tauri's create-dmg needs Finder automation and timed out). The self-test run against the built `.app` passes using only the
  bundle's own backend and templates. Signature is ad-hoc (no Developer ID yet);
  `src-tauri/entitlements.plist` and `tools/sign_backend_macos.sh` are ready for Developer ID
  signing + notarisation.
* **Playwright end-to-end** (`apps/desktop/e2e`, browser mock mode): sign-in, full wizard through
  the email draft, stale-PDF handling, settings (mailbox connect, output folder, offline toggle,
  reachability). 4 tests, ~20 s. Tauri's WebDriver has no macOS support, so the Rust/Python chain
  stays covered by the self-test and pytest.
* **CI** (`.github/workflows/ci.yml`): macOS (Apple Silicon) and Windows runners: pytest, template
  lint, Vitest, cargo test, Playwright, backend build, `tauri-action` build, self-test of the built
  app, artifact upload; signing activates when the Apple/Windows secrets exist.
* **Licenses**: `tools/licenses.py` → `docs/THIRD_PARTY_LICENSES.md` from the real trees
  (13 Python, 87 npm, 469 Rust packages); no GPL/AGPL bundled; docxtpl (LGPL) shipped as
  replaceable bytecode in the one-dir folder.
* **Docs**: `docs/install.md`, `docs/troubleshooting.md`, `docs/release.md`.
* **Not done here**: the Windows build has not been executed (no Windows machine); the CI workflow
  is written but has not run yet (needs a GitHub remote); notarisation needs your Apple Developer ID.

## 2026-11-06 — Offline by default (user requirement: "always make sure the app runs offline")
* `offline_mode` default is now **true**; the mailbox features require an explicit opt-in.
* Process-wide socket guard (`net.install_guard`): `socket.connect`/`connect_ex` raise `OfflineMode`
  for any IPv4/IPv6 address while offline — a backstop beneath the IMAP module's own check.
* Email step shows why the mailbox option is unavailable; Privacy card says "On by default".
* Tests: `test_socket_guard_blocks_raw_connections_while_offline`; offline-by-default assertions;
  e2e updated. The offline acceptance test (sockets disabled → everything works) still passes.

## 2026-11-07 — Windows build via CI; repository on GitHub
* Repository: private `pratik24mac/papyra` (history squashed to one clean commit without the
  confidential source documents; originals live in the ignored `private/` folder; bundled fixture
  is a synthetic person).
* CI fixes needed to get the first green Windows job: `macos-latest` runner label; Windows-safe
  unwritable-folder test; LibreOffice located through the backend locator in tests; Playwright specs
  excluded from Vitest; fidelity tests convert through the backend (valid profile URI on Windows);
  frontend build + backend staging before `cargo test` (Tauri codegen needs `../dist` and the
  resource glob); Apple signing variables exported only when the secret exists.
* **Windows job green (run 42268971479)**: pytest (fidelity regression included, LibreOffice from
  choco), Vitest, cargo test, Playwright, backend one-dir, Tauri build → `Papyra_0.1.0_x64-setup.exe`
  (17 MB, NSIS) and `Papyra_0.1.0_x64_en-US.msi` (22 MB), self-test of the built app passed,
  artifact uploaded. Not yet installed by a human on a Windows PC.

## 2026-11-21 — LibreOffice timeout on slow Windows PCs
Cause: a fresh temporary LibreOffice profile per conversion, so every document paid LibreOffice's
first-start work (font cache, registry, extensions) plus the antivirus scan of its libraries:
about a second on the Mac, over the 120 s limit on a low-end Windows PC.
Fix (`pdfconv/libreoffice.py`): persistent private profile in `<data>/lo-profile`, pre-seeded with
the update check and first-run dialogs disabled; warmed in a background thread at engine start
(`DOCMASTER_WARMUP=0` disables, used by tests); cold conversion allowed 900 s, warm ones 180 s;
a failed attempt rebuilds the profile and retries once; partial output folders are removed on
failure; diagnostics report `profile_warm`; the progress message explains a slow first start; the
Rust call timeout for `docgen.*` is 1200 s. Troubleshooting documents the Defender exclusion.
Tests: `tests/test_pdfconv.py` (warm-up, reuse, seeded settings, rebuild-on-failure, timeouts).

## 2026-11-21 — Templates added by folder, in the installed app
* Catalogue scans two roots: bundled (`resources/templates`) and the user folder
  `<output-dir default>/templates` (`--user-templates-dir`; created on start with a README).
* Rescan on every listing (cheap signature of schema/docx mtimes) + `templates.rescan`; the template
  screen rescans on window focus and has Rescan / "My templates folder" buttons.
* Lint on load: a template with a broken schema, missing file or linter error is listed with
  `status: error` and its problems ("needs fixing" card with "Open folder to fix"); a user template
  reusing a bundled id is reported, never silently overriding. Highest version wins per id.
* `templates.example_values` serves `values.example.yaml` from the template's own folder (replaces
  the Rust dev helper, which only knew the bundled v1 path).
* Tests: `tests/test_user_templates.py`. Guide updated (section 5).

## 2026-11-21 — Windows: LibreOffice hang, not slowness
Evidence from the user's PC: warm-up converted in 35 s, every later conversion timed out, two
LibreOffice processes idle at 0 % CPU. On Windows `soffice.exe` is a launcher for `soffice.bin`;
a timeout killed only the launcher, the orphaned `soffice.bin` kept the profile's pipe, and each
new launcher handed its job to the wedged orphan and waited. A profile rebuild does not help
because the pipe name derives from the profile path.
Fix (`pdfconv/libreoffice.py`, psutil): kill any process using our profile before a run and after
it; kill the whole process tree on timeout; stall detection (no CPU activity and no output for
75 s → "LibreOffice stopped responding", tree killed, profile rebuilt, one retry); successful
conversions logged with their duration. Tests use a shell-script stand-in for soffice.

## 2026-11-21 — Diagnostics and packaging guard
The user's own Windows build shipped an engine without `psutil` (stale venv) and crashed on
the first conversion with a bare "internal error". Now: `selfcheck.py` checks every runtime
module at engine start and refuses to start (exit 3, FATAL line) when one is missing;
`tools/build_backend.py` runs the same preflight and refuses to package; RPC crashes carry the
exception type and message; `system.selfcheck` (Settings → Diagnostics → Run full check) checks
modules, LibreOffice, leftover processes and a real test conversion with timings, and returns the
last 40 log lines; "Copy report" copies it all. Tests: `tests/test_selfcheck.py`.

## 2026-11-21 — Readiness gate
After sign-in the UI runs `system.selfcheck` without the test conversion; a failing module,
missing LibreOffice or a broken engine shows a blocking "Setup required" screen (what is missing,
fix text, Get LibreOffice button, Check again, Open diagnostics). The Rust supervisor now keeps the
engine's last stderr line and, on exit code 3 or a FATAL line, reports it as the failure reason at
once instead of restarting three times. e2e: setup gate test.

## 2026-11-22 — Document quality: dates, images, last page
* `docgen/dates.py`: portable token formats (D, DD, Do, M…MMMM, YY, YYYY, ddd, dddd; `%` switches
  to strftime). Precedence field `format` → template `date_format` → setting `date_format`
  (Settings → Dates, presets + custom, validated) → `D MMMM YYYY`. Jinja filter `date` for
  per-tag formats; dates inside group_list items formatted too.
* PDF export now passes JSON filter options: lossless images, no downsampling, quality 100,
  tagged PDF, bookmarks. Test checks a 2400×1200 image survives at full size without DCT.
* `ooxml.trim_trailing_blank`: removes empty paragraphs/page breaks at the end of the body; keeps
  the mandatory paragraph after a final table but shrinks it to 1 pt; `template.trim_trailing_blank:
  false` opts out. Applied after every render.
* Tests: `tests/test_document_quality.py`.

## 2026-11-22 — PDF-level watermark; ordinal date presets
* Lossless export did not fix the user's blurry, resized, darker watermark: LibreOffice re-renders
  Word's header watermark shape. New `pdfconv/watermark.py`: `template.watermark` (image, opacity,
  scale, rotation, position, pages) stamps the original image *behind* each page's content as a
  Flate-compressed XObject at native resolution, washout computed by compositing onto white;
  `ooxml.strip_word_watermarks` removes Word's PowerPlusWaterMarkObject/WordPictureWatermark shapes
  from all headers when a PDF watermark is configured. Applied in generate and re-convert; linter
  S006 checks the image exists. Pillow is now a runtime dependency (was excluded from the bundle).
* Date presets gained ordinal forms: "March 12th, 2026", "Thursday, March 12th, 2026".

## 2026-11-22 — Date picker freeze / blank screen; autocomplete off
Cause found: an unquoted date in `values.example.yaml` or a schema `default:` is a Python `date`
after YAML parsing; the RPC encoder could not serialise it, the response was never sent, and the
UI waited forever (freeze) or rendered nothing. Fixes: `json_default` in the RPC encoder (dates →
ISO, paths → str), unserialisable results now answered with an INTERNAL_ERROR instead of silence,
catalogue normalises YAML dates to ISO strings in schemas and example values; the date control
accepts only strict ISO strings (anything else renders empty rather than an invalid date); an
error boundary (app-wide and per screen) shows the error with Copy details instead of a blank
window. All document forms and inputs have `autocomplete="off"` (sign-in keeps it for password
managers). e2e: `e2e/date.spec.ts` (typing, calendar click, review round trip, bad default, autocomplete).
