# Security and privacy review — Papyra (Phase 5, 2026-11-03)

Scope: the desktop app (Tauri 2 shell + React UI), the Python backend sidecar, generated files,
settings, credentials, logs and network use. Reviewed against spec §10 (offline-first) and §11.

## 1. Trust boundaries and IPC surface
| Boundary | Control | Status |
|----------|---------|--------|
| WebView → Rust | Only commands in `generate_handler!`; every one calls `require_auth` except `login`, `auth_status`, `backend_status` | ✅ |
| WebView → backend | Single command `backend_call` with a **closed allow-list** (`ALLOWED_METHODS`); `system.shutdown` is not callable from the UI; `tests/test_contract.py` keeps Python, Rust and TypeScript lists in sync | ✅ |
| WebView → filesystem | No `fs`/`shell`/`http`/`dialog` plugin permissions in `capabilities/default.json` (core only). Files are addressed by job id; Rust resolves paths through the backend and rejects anything outside the current output folder (`files.rs`) | ✅ |
| WebView content | CSP: `default-src 'self'`; no remote scripts, images limited to self/data/blob, worker-src for pdf.js only; `devUrl` only in dev | ✅ |
| Rust → backend | stdio JSON-RPC, process owned by Rust, no listening socket, no port | ✅ |
| Backend → OS | LibreOffice spawned with an isolated profile and a timeout; output confined to the output folder; job ids validated (`^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`) | ✅ |

## 2. Authentication
Fixed credentials verified in Rust: salted SHA-256, constant-time comparison, incremental delay
after failures; the password is not stored. Session state lives in Rust memory only.
*Limitation*: a single shared account; no per-user audit trail. Acceptable for a single-user
desktop app; revisit if the app is deployed to shared machines.

## 3. Secrets
* Mailbox password: OS keychain via `keyring`, chunked for Windows; never in settings.json,
  job.json, history.db, logs or RPC responses (`email.imap_get_account` returns `has_password` only).
* No API keys exist (Gmail/Graph were dropped). Nothing is embedded in the frontend bundle.

## 4. Data at rest
| Data | Location | Personal data |
|------|----------|---------------|
| Generated DOCX/PDF/.eml + `job.json` (paths, hashes) | output folder, one sub-folder per job | yes (the documents themselves) |
| `history.db` (template, time, paths, pages, draft outcome) | app data dir | metadata only |
| `settings.json` (output folder, mail server/address, toggles) | app data dir | email address only |
| Logs (rotating, 1 MB × 3) | app data dir `logs/` | redacted (emails, secrets, long numbers) |
Form values are never persisted. Deletion: per job (with or without files), all documents and
history, logs and temp files — all from Settings → Privacy. Temp LibreOffice profiles are
removed after every conversion; a startup sweep removes leftovers.

## 5. Network
* The backend opens exactly one kind of connection: IMAP over TLS to the configured host, only
  on an explicit user action (test, connect, create draft, reachability check).
* **Offline mode is on by default** (Settings → Privacy) and blocks even that. It is enforced twice in
  the backend: the IMAP module refuses with a clear error, and a process-wide socket guard
  (`net.install_guard`) makes `socket.connect` raise for any IPv4/IPv6 address while offline, so no
  current or future code path can open a connection. The user opts in explicitly to use the mailbox.
* **Offline acceptance test** (`tests/test_privacy.py`): with Python socket creation disabled,
  validation, DOCX generation, PDF conversion, .eml creation and history all succeed.
* No telemetry, no update check, no remote templates, no cloud conversion.
* VPN: the IMAP connection follows the system route like any other app; the reachability check
  reports DNS, TCP and TLS stages separately so VPN/DNS blocking is diagnosable. Certificate
  validation uses the system trust store (`ssl.create_default_context`).
* `.eml` is the fully offline alternative when a network is untrusted.

## 6. Known gaps / follow-ups
1. Code signing and notarisation (Phase 6) — unsigned dev builds trigger Gatekeeper and keychain prompts.
2. One-file PyInstaller (dev) runs as two processes; the product build switches to one-dir (Phase 6).
3. The template linter runs in CI and the dev CLI, not at app start (templates are bundled and read-only).
4. SQLite file is unencrypted; it holds metadata only. Full-disk encryption (FileVault/BitLocker) is the recommended protection for the output folder.
5. Logs from the Rust shell (stderr) are not written to disk in dev; production builds should route them through the same redacting file logger.
