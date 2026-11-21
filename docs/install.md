# Installing Papyra

## Requirements
* macOS 12 or later (Apple Silicon build; Intel on request) or Windows 10/11 64-bit.
* **LibreOffice** (free, https://www.libreoffice.org/download/) for PDF conversion. Papyra finds it
  automatically in the standard location; Settings → Diagnostics shows whether it was found.
  Without it, Word documents are still generated; PDF and email steps are unavailable.
* No internet connection is needed, ever. Papyra starts in **offline mode**: it will not open a
  single network connection until you turn offline mode off in Settings → Privacy, which you only
  need for saving email drafts to your own mailbox.

## macOS
1. Open the `.dmg` and drag Papyra to Applications.
2. First launch: if the build is not notarised yet, macOS shows "cannot be opened because the
   developer cannot be verified". Right-click the app → **Open** → **Open**. This is needed once.
3. The first launch takes 10–20 seconds while macOS scans the new application; later launches are
   instant.
4. Sign in (default `admin` / `DocMaster!2026`; change it before sharing the machine — see the
   release guide).

## Windows
1. Run the installer (`Papyra_x.y.z_x64-setup.exe`). It installs for the current user, no admin
   rights needed.
2. If SmartScreen appears on an unsigned build: **More info** → **Run anyway**.
3. Install LibreOffice to `C:\Program Files\LibreOffice` (the default).

## Start-up check
Every start, after sign-in, Papyra verifies its own packaging, LibreOffice and the templates. If
anything is missing it shows a **Setup required** screen with what to install and a "Get
LibreOffice" button; click **Check again** afterwards, no restart needed. Nothing can be
generated until the check passes.

## Where Papyra keeps things
| What | macOS | Windows |
|------|-------|---------|
| Generated documents | `~/Documents/Papyra/<job>/` (changeable in Settings) | `Documents\Papyra\<job>\` |
| Settings, history, logs | `~/Library/Application Support/com.papyra.desktop/` | `%APPDATA%\com.papyra.desktop\` |
| Mailbox password | Keychain | Credential Manager |

Everything can be deleted from Settings → Privacy & network.
