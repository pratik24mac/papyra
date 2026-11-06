# Papyra desktop (Tauri 2) — Phase-1 proof of concept

Proves the architecture's riskiest claim: a Tauri shell supervising a packaged Python backend
over JSON-RPC on stdin/stdout, with no local HTTP server.

## Layout
```
apps/desktop/
├── src/                 React UI (PoC page with buttons + log; the product UI comes in Phase 2)
├── src-tauri/
│   ├── src/backend.rs   sidecar supervisor + JSON-RPC client (ids, timeouts, notifications → events)
│   ├── src/lib.rs       commands exposed to the WebView (`backend_call` with an allow-list) + self-test
│   ├── resources/       one-dir PyInstaller backend + bundled templates (built by tools/build_backend.py, not committed)
│   ├── capabilities/    WebView permissions: core only — no fs/shell/http plugins
│   └── tauri.conf.json  window, CSP, externalBin
└── dist/                built frontend (generated)
```

## Prerequisites (macOS)
* Node 20+, Rust stable (`brew install rustup && rustup toolchain install stable`)
* Python 3.12 venv at the repo root: `python3.12 -m venv .venv && .venv/bin/pip install -r tools/requirements.txt pyinstaller`
* LibreOffice (`brew install --cask libreoffice`)

## Build the backend (one-dir, staged as a Tauri resource together with the templates)
```bash
.venv/bin/python tools/build_backend.py
```

## Release build
See `docs/release.md`. End-to-end UI tests: `npx playwright test` (browser mock mode).

## Run
```bash
cd apps/desktop && npm install && npm run tauri dev
```

## Automated self-test (no clicking)
Builds the frontend, compiles the app, starts it with the sidecar, runs ping → diagnostics →
templates → invalid values → full generate (DOCX + PDF) → ping, prints one line per step and exits 0/1.
```bash
cd apps/desktop && npm run build && (cd src-tauri && cargo build) && \
  DOCMASTER_SELFTEST=1 DOCMASTER_OUTPUT_DIR=/tmp/docmaster-selftest ./src-tauri/target/debug/papyra
```

## Email
Settings → Email account stores the IMAP details in `settings.json` and the password in the OS keychain.
The self-test never touches the keychain. Drafts are appended to the Drafts folder; the app never sends.

## Environment variables
| Variable | Purpose |
|----------|---------|
| `DOCMASTER_TEMPLATES_DIR` | override the templates folder (default: repo `templates/` in debug, app resources in release) |
| `DOCMASTER_OUTPUT_DIR` | override the output folder (default: `~/Documents/Papyra`) |
| `DOCMASTER_SELFTEST` | run the self-test and exit |
| `DOCMASTER_SOFFICE` | explicit LibreOffice path for the backend |

Note: `cargo test --lib` and `cargo build` need `src-tauri/resources/backend` to exist (the Tauri build script resolves the resource globs), so run `tools/build_backend.py` once after cloning.
