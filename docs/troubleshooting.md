# Troubleshooting

| Symptom | Cause | What to do |
|---------|-------|------------|
| Badge says "Engine starting…" for a long time on first launch | macOS/Windows scanning the new backend binary | Wait up to 30 s once; later launches take under a second |
| "Engine unavailable" | The backend crashed 3 times | Settings → Privacy → Open data folder → `logs/backend.log`; restart the app; reinstall if it persists |
| "LibreOffice is not installed" | Not found at the standard path | Install LibreOffice, or set `DOCMASTER_SOFFICE` to the `soffice` executable; check Settings → Diagnostics |
| PDF conversion failed, Word document kept | LibreOffice error or timeout (default 120 s) | Open the Word file to check it; retry; very large documents may need the timeout raised |
| "The PDF is out of date" | The Word file was edited after the PDF was made | Preview → **Regenerate PDF** (the app refuses to attach a stale PDF) |
| "Mailbox sign-in failed" | Wrong address/password, or the provider requires an app password | Re-enter in Settings → Email account; for Porkbun use the full address as username |
| "Mail server unreachable" only on VPN | VPN or its DNS blocks port 993 | Settings → Privacy → **Check mail server reachability** shows which stage fails; ask the VPN admin to allow IMAP, or save a `.eml` file |
| "Offline mode is on" | You enabled it in Privacy | Turn it off to use the mailbox |
| Keychain prompt on connecting the mailbox | Unsigned dev build asking for keychain access | Click Always Allow; signed builds do not prompt |
| `.eml` opens as a received message in Apple Mail | Apple Mail does not import drafts | Use Forward, or prefer the IMAP draft |
| Dev: "Port 5173 is already in use" | A previous `tauri dev` Vite process is still running | `lsof -i :5173 -t | xargs kill` |

Logs never contain form values, email addresses or passwords. Attach `backend.log` when reporting a problem.
