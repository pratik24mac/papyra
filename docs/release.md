# Building and releasing

## Local build (macOS)
```bash
.venv/bin/pytest -q tests && (cd apps/desktop && npx vitest run && npx playwright test)
.venv/bin/python tools/build_backend.py        # one-dir backend + templates → src-tauri/resources/
.venv/bin/python tools/licenses.py             # refresh docs/THIRD_PARTY_LICENSES.md
cd apps/desktop && npm run tauri build -- --bundles app   # .app only
cd ../.. && tools/make_dmg_macos.sh                     # DMG via hdiutil (no Finder automation needed)
```
Output: `apps/desktop/src-tauri/target/release/bundle/{macos/Papyra.app, dmg/Papyra_<v>_aarch64.dmg}`.
Tauri's own `--bundles dmg` styles the window through Finder/AppleScript and fails without an
interactive session ("AppleEvent timed out"); the script above is the reliable path and is what CI uses.
Verify the bundle without clicking: `DOCMASTER_SELFTEST=1 Papyra.app/Contents/MacOS/papyra`.

## Local build (Windows)
Same steps in PowerShell with `.venv\Scripts\...`; `npm run tauri build` produces an NSIS
installer under `bundle\nsis\`. Requires the Visual Studio C++ build tools and WebView2 (preinstalled on Windows 11).

## CI
`.github/workflows/ci.yml` runs tests and builds both platforms on every push; artifacts are
attached to the run. Signing happens automatically when the secrets below exist.

## Code signing and notarisation
* **macOS**: Developer ID Application certificate. Set `APPLE_SIGNING_IDENTITY` (and for CI the
  `APPLE_CERTIFICATE`/`APPLE_CERTIFICATE_PASSWORD` base64 export) plus `APPLE_ID`,
  `APPLE_PASSWORD` (app-specific), `APPLE_TEAM_ID` for notarisation. Tauri signs the app bundle;
  the backend folder is a resource, so sign its Mach-O files first:
  `tools/sign_backend_macos.sh "<identity>"` (run after `build_backend.py`, before `tauri build`).
  Hardened-runtime entitlements for the Python runtime are in `src-tauri/entitlements.plist`.
* **Windows**: an Authenticode certificate (OV/EV). Configure `bundle.windows.certificateThumbprint`
  or sign the installer with `signtool` after the build.

## Versioning
Bump `version` in `apps/desktop/src-tauri/tauri.conf.json`, `apps/desktop/package.json`,
`apps/desktop/src-tauri/Cargo.toml` and `backend/pyproject.toml` together; tag `vX.Y.Z`.
Template changes get a new `templates/<id>/vN/` folder, never an in-place edit.

## Changing the sign-in credentials
`.venv/bin/python tools/set_password.py <user> <password>` then rebuild.
