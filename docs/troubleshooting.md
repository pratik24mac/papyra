# Troubleshooting

| Symptom | Cause | What to do |
|---------|-------|------------|
| Badge says "Engine starting…" for a long time on first launch | macOS/Windows scanning the new backend binary | Wait up to 30 s once; later launches take under a second |
| "Engine unavailable" | The backend crashed 3 times | Settings → Privacy → Open data folder → `logs/backend.log`; restart the app; reinstall if it persists |
| "LibreOffice is not installed" | Not found at the standard path | Install LibreOffice, or set `DOCMASTER_SOFFICE` to the `soffice` executable; check Settings → Diagnostics |
| First PDF takes minutes, or "LibreOffice did not finish within … s" | LibreOffice's first start on this computer (font cache, registry, antivirus scan of its libraries) | Papyra warms its private LibreOffice profile in the background after the engine starts; wait a minute after launch before generating the first document. The first conversion is allowed 15 minutes, later ones 3. On slow PCs add a Windows Defender exclusion for `C:\Program Files\LibreOffice` (Windows Security → Virus & threat protection → Exclusions): it roughly halves start-up time. Settings → Diagnostics shows "profile warm" when the one-off work is done |
| "internal error: ModuleNotFoundError" or the engine does not start after a local build | The engine was packaged from a venv missing a dependency | `pip install -r tools/requirements.txt`, then rebuild with `tools/build_backend.py` (it now refuses to build with a missing module). Settings → Diagnostics → **Run full check** lists every module |
| "LibreOffice stopped responding" (Windows) | A LibreOffice process from an earlier run was left behind holding Papyra's profile; every later conversion handed its job to it and waited | Papyra now kills such leftovers before each conversion and detects a hang within about a minute. If it still happens, end all LibreOffice processes in Task Manager and generate again |
| PDF has one more page than the Word document | Trailing empty paragraphs/page break (removed automatically since 2026-11-22), or text reflow from a font missing on this machine | Open the generated .docx in Word: if Word also shows the extra page, the template ends with blank paragraphs inside a table or section; otherwise install the template's fonts or switch to a common font |
| Watermark blurry, bigger or darker than in Word | LibreOffice re-renders Word's watermark shape | Declare the watermark in the template schema (`template.watermark`, see the authoring guide): Papyra then stamps the original image into the PDF itself, at exact size and opacity |
| Other images blurry in the PDF | Fixed 2026-11-22: export is lossless at full resolution | The source image itself must have enough pixels |
| Different date formats across documents | Each template printed the raw value | Settings → Dates sets one format; a template or field can override it |
| PDF conversion failed, Word document kept | LibreOffice error | Open the Word file to check it; retry: Papyra rebuilds its LibreOffice profile automatically on the second attempt |
| "The PDF is out of date" | The Word file was edited after the PDF was made | Preview → **Regenerate PDF** (the app refuses to attach a stale PDF) |
| "Mailbox sign-in failed" | Wrong address/password, or the provider requires an app password | Re-enter in Settings → Email account; for Porkbun use the full address as username |
| "Mail server unreachable" only on VPN | VPN or its DNS blocks port 993 | Settings → Privacy → **Check mail server reachability** shows which stage fails; ask the VPN admin to allow IMAP, or save a `.eml` file |
| "Offline mode is on" | You enabled it in Privacy | Turn it off to use the mailbox |
| Keychain prompt on connecting the mailbox | Unsigned dev build asking for keychain access | Click Always Allow; signed builds do not prompt |
| `.eml` opens as a received message in Apple Mail | Apple Mail does not import drafts | Use Forward, or prefer the IMAP draft |
| Dev: "Port 5173 is already in use" | A previous `tauri dev` Vite process is still running | `lsof -i :5173 -t | xargs kill` |

**Diagnosing anything**: Settings → Diagnostics → **Run full check** verifies the engine's packaging, LibreOffice, leftover processes and a real test conversion, shows the recent log, and **Copy report** puts it all on the clipboard.

Logs never contain form values, email addresses or passwords. Attach `backend.log` when reporting a problem.
