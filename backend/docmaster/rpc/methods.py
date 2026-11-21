"""The closed list of RPC methods. Each maps 1:1 to a Tauri command."""
from __future__ import annotations
import os, platform, sys, time, uuid
from pathlib import Path
from .. import __version__
from ..docgen.ooxml import set_document_properties
from ..docgen.render import render_docx, validate
from ..storage.jobs import JobRecord, JobStore
from ..storage.settings import Settings
from ..storage.history import History
from ..storage.cleanup import sweep_output, sweep_temp
from .. import net
import logging
from ..email.mime import DraftSpec
from ..email.eml import write_eml
from ..email import imap_draft
from ..secrets.credential_store import CredentialStore
from ..errors import EmailAccountMissing, PdfStale
from datetime import datetime, timezone
from ..errors import PdfConversionFailed, PdfInvalid
from docx import Document
from ..pdfconv import libreoffice
from ..pdfconv.libreoffice import convert_to_pdf, find_soffice, soffice_version, validate_pdf
from ..storage.paths import ensure_dir, filename_from_pattern, unique_path
from ..templates.catalogue import Catalogue


def build_methods(templates_dir: Path, output_dir: Path, soffice_override: str | None = None, data_dir: Path | None = None,
                  credentials: CredentialStore | None = None, imap_factory=None, user_templates_dir: Path | None = None) -> dict:
    user_templates_dir = user_templates_dir or output_dir / "templates"
    try: Catalogue.ensure_user_root(user_templates_dir)
    except OSError: pass
    catalogue = Catalogue(templates_dir, user_templates_dir)
    settings = Settings(data_dir or output_dir.parent / ".papyra", output_dir)
    jobs = JobStore(settings.output_dir())            # re-pointed on every call via current_jobs()
    creds = credentials or CredentialStore()
    history = History(settings.path.parent)
    # persistent LibreOffice profile: first-start cost once per installation, warmed in the background
    libreoffice.configure(settings.path.parent / "lo-profile")
    if os.environ.get("DOCMASTER_WARMUP", "1") != "0" and find_soffice(soffice_override):
        libreoffice.warm_profile_async(find_soffice(soffice_override))
    log = logging.getLogger("docmaster.methods")

    def sync_offline():
        imap_draft.OFFLINE["enabled"] = bool(settings.all().get("offline_mode"))

    net.install_guard(lambda: bool(settings.all().get("offline_mode", True)))   # backstop: no sockets while offline

    def current_jobs() -> JobStore:
        jobs.output_dir = settings.output_dir()
        return jobs

    def system_ping(ctx):
        return {"name": "docmaster-backend", "version": __version__, "pid": os.getpid(),
                "python": platform.python_version(), "frozen": bool(getattr(sys, "frozen", False))}

    def system_shutdown(ctx):
        return {"ok": True}

    def system_diagnostics(ctx):
        soffice = find_soffice(soffice_override)
        writable = True
        try: ensure_dir(settings.output_dir())
        except Exception: writable = False  # noqa: BLE001
        return {"templates_dir": str(templates_dir), "user_templates_dir": str(user_templates_dir), "templates": len([t for t in catalogue.list() if t["status"] == "ok"]),
                "output_dir": str(settings.output_dir()), "output_dir_writable": writable, "data_dir": str(settings.path.parent),
                "libreoffice": {"found": soffice is not None, "path": str(soffice) if soffice else None,
                                "version": soffice_version(soffice) if soffice else None,
                                "profile_warm": libreoffice.profile_is_warm(), "profile_dir": str(settings.path.parent / "lo-profile")},
                "platform": platform.platform(), "python": platform.python_version()}

    def system_selfcheck(ctx, convert: bool = True):
        from ..selfcheck import run as selfcheck_run
        return selfcheck_run(soffice_override, settings.path.parent, convert=convert)

    def templates_list(ctx):
        return {"templates": catalogue.list(), "user_templates_dir": str(user_templates_dir)}

    def templates_rescan(ctx):
        changed = catalogue.reload(force=True)
        return {"changed": changed, "templates": catalogue.list(rescan=False), "user_templates_dir": str(user_templates_dir)}

    def templates_example_values(ctx, template_id: str):
        return {"values": catalogue.example_values(template_id)}

    def docgen_generate(ctx, template_id: str, values: dict, job_id: str | None = None):
        job_id = job_id or uuid.uuid4().hex
        t0 = time.monotonic()
        tpl = catalogue.get(template_id)
        meta = tpl.schema["template"]
        ctx.progress(job_id=job_id, stage="validating", message="Checking values")
        validate(tpl.schema, values)                     # fail before anything touches the disk
        out_dir = ensure_dir(settings.output_dir() / job_id)
        stem = filename_from_pattern(meta.get("output_filename", "{date}-" + template_id), values)
        docx_path = unique_path(out_dir, stem, ".docx")
        ctx.progress(job_id=job_id, stage="rendering_docx", message="Generating Word document")
        render_docx(tpl.docx, tpl.schema, values, docx_path)
        d = Document(docx_path); set_document_properties(d, f"{meta['name']} — {stem}", subject=meta["name"]); d.save(docx_path)
        rec = JobRecord.new(job_id, template_id, tpl.version, docx_path, meta.get("expected_pages")); current_jobs().save(rec)
        if settings.all().get("keep_history", True): history.record_job(job_id, template_id, tpl.version, "docx_done", settings.output_dir(), docx_path)
        ctx.progress(job_id=job_id, stage="docx_done", message="Word document created", docx_path=str(docx_path))
        ctx.progress(job_id=job_id, stage="converting_pdf", message="Converting to PDF" if libreoffice.profile_is_warm()
                     else "Starting LibreOffice for the first time on this computer; this can take a few minutes once")
        try:
            pdf_path, seconds = convert_to_pdf(docx_path, find_soffice(soffice_override))
            pages = validate_pdf(pdf_path, meta.get("expected_pages"),
                                 [str(values.get(k, "")) for k in meta.get("essential_text", [])])
        except (PdfConversionFailed, PdfInvalid) as e:
            e.data.setdefault("docx_path", str(docx_path)); e.data["job_id"] = job_id
            rec.status, rec.error = "pdf_failed", {"code": e.code, "message": str(e)}; current_jobs().save(rec)
            if settings.all().get("keep_history", True): history.record_job(job_id, template_id, tpl.version, "pdf_failed", settings.output_dir(), docx_path, error_code=e.code)
            raise
        rec.set_pdf(pdf_path, pages); current_jobs().save(rec)
        if settings.all().get("keep_history", True): history.record_job(job_id, template_id, tpl.version, "pdf_done", settings.output_dir(), docx_path, pdf_path, pages)
        ctx.progress(job_id=job_id, stage="pdf_done", message=f"PDF created ({pages} pages)", pdf_path=str(pdf_path))
        return {"job_id": job_id, "template_id": template_id, "template_version": tpl.version,
                "docx_path": str(docx_path), "pdf_path": str(pdf_path), "pages": pages,
                "docx_sha256": rec.docx_sha256, "pdf_sha256": rec.pdf_sha256,
                "pdf_seconds": round(seconds, 2), "total_ms": int((time.monotonic() - t0) * 1000)}

    def jobs_get(ctx, job_id: str):
        """Current state of a job's files: used before preview/email to refuse a stale PDF."""
        rec = current_jobs().load(job_id)
        return {"job": rec.__dict__, "state": rec.current_state(), "output_dir": str(settings.output_dir())}

    def docgen_convert_pdf(ctx, job_id: str):
        """Re-create the PDF from the DOCX as it is now (after an external edit)."""
        rec = current_jobs().load(job_id)
        docx_path = Path(rec.docx_path)
        if not docx_path.exists():
            raise PdfConversionFailed("the Word document no longer exists", data={"job_id": job_id, "docx_path": rec.docx_path})
        ctx.progress(job_id=job_id, stage="converting_pdf", message="Converting to PDF" if libreoffice.profile_is_warm()
                     else "Starting LibreOffice for the first time on this computer; this can take a few minutes once")
        rec.docx_sha256 = JobRecord.new(job_id, rec.template_id, rec.template_version, docx_path, rec.expected_pages).docx_sha256
        try:
            pdf_path, seconds = convert_to_pdf(docx_path, find_soffice(soffice_override))
            pages = validate_pdf(pdf_path, rec.expected_pages)        # text may legitimately differ after an edit
        except (PdfConversionFailed, PdfInvalid) as e:
            e.data.setdefault("docx_path", str(docx_path)); e.data["job_id"] = job_id
            rec.status, rec.error = "pdf_failed", {"code": e.code, "message": str(e)}; current_jobs().save(rec)
            raise
        rec.set_pdf(pdf_path, pages); current_jobs().save(rec)
        if settings.all().get("keep_history", True): history.record_job(job_id, rec.template_id, rec.template_version, "pdf_done", settings.output_dir(), docx_path, pdf_path, pages)
        ctx.progress(job_id=job_id, stage="pdf_done", message=f"PDF created ({pages} pages)", pdf_path=str(pdf_path))
        return {"job_id": job_id, "pdf_path": str(pdf_path), "pages": pages, "docx_sha256": rec.docx_sha256,
                "pdf_sha256": rec.pdf_sha256, "pdf_seconds": round(seconds, 2)}

    def settings_get(ctx):
        return settings.all()

    def settings_set(ctx, key: str, value=None):
        return settings.set(key, value)

    # ---------------- email ----------------
    def _fresh_pdf_job(job_id: str):
        rec = current_jobs().load(job_id)
        st = rec.current_state()
        if st["pdf_stale"]:
            raise PdfStale(data={"job_id": job_id})
        return rec

    def _record_draft(rec, entry: dict):
        rec.drafts.append({"created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}); current_jobs().save(rec)

    def email_prepare_eml(ctx, job_id: str, message: dict):
        rec = _fresh_pdf_job(job_id)
        acct = settings.all().get("imap_account")
        spec = DraftSpec.from_dict(message, sender=(acct or {}).get("email"))
        path = write_eml(spec, Path(rec.pdf_path))
        rec.eml_path = str(path); _record_draft(rec, {"mode": "eml", "status": "saved", "path": str(path)})
        if settings.all().get("keep_history", True): history.record_draft(job_id, "eml", "saved", str(path))
        return {"job_id": job_id, "eml_path": str(path), "bytes": path.stat().st_size, "attachment": Path(rec.pdf_path).name}

    def email_imap_get_account(ctx):
        acct = settings.all().get("imap_account")
        if not acct:
            return {"configured": False}
        has_pw = creds.get(f"imap:{acct['email']}") is not None
        return {"configured": True, "has_password": has_pw, **acct}

    def email_imap_test(ctx, account: dict | None = None, password: str | None = None):
        sync_offline()
        acct = imap_draft.ImapAccount.from_dict(account or settings.all().get("imap_account") or {})
        pw = password if password is not None else creds.get(f"imap:{acct.email}")
        if pw is None:
            raise EmailAccountMissing()
        return imap_draft.test_connection(acct, pw, factory=imap_factory) | {"email": acct.email}

    def email_imap_save_account(ctx, account: dict, password: str, verify: bool = True):
        sync_offline()
        acct = imap_draft.ImapAccount.from_dict(account)
        result = imap_draft.test_connection(acct, password, factory=imap_factory) if verify else {"ok": True, "drafts_folder": acct.drafts_folder}
        creds.set(f"imap:{acct.email}", password)
        settings.set("imap_account", acct.public() | {"drafts_folder": result.get("drafts_folder")})
        return email_imap_get_account(ctx)

    def email_imap_remove_account(ctx):
        acct = settings.all().get("imap_account")
        if acct:
            creds.delete(f"imap:{acct['email']}")
            settings.set("imap_account", None)
        return {"configured": False}

    def email_create_imap_draft(ctx, job_id: str, message: dict):
        sync_offline()
        acct_d = settings.all().get("imap_account")
        if not acct_d:
            raise EmailAccountMissing()
        acct = imap_draft.ImapAccount.from_dict(acct_d)
        pw = creds.get(f"imap:{acct.email}")
        if pw is None:
            raise EmailAccountMissing("the mailbox password is missing from the credential store")
        rec = _fresh_pdf_job(job_id)
        spec = DraftSpec.from_dict(message, sender=acct.email)
        from ..email.mime import build_message
        ctx.progress(job_id=job_id, stage="email_connecting", message=f"Connecting to {acct.host}")
        res = imap_draft.append_draft(acct, pw, build_message(spec, Path(rec.pdf_path)), factory=imap_factory)
        _record_draft(rec, {"mode": "imap", "status": "saved", "folder": res["folder"], "uid": res.get("uid"), "account": acct.email})
        if settings.all().get("keep_history", True): history.record_draft(job_id, "imap", "saved", res["folder"])
        return {"job_id": job_id, "account": acct.email, **res, "attachment": Path(rec.pdf_path).name}

    # ---------------- history / privacy / network ----------------
    def history_list(ctx, limit: int = 50, offset: int = 0):
        return {"jobs": history.list(limit, offset), "total": history.count()}

    def history_delete(ctx, job_id: str, delete_files: bool = False):
        from ..storage.jobs import check_job_id
        return history.delete(check_job_id(job_id), bool(delete_files))

    def history_clear(ctx, delete_files: bool = False):
        return history.clear(bool(delete_files))

    def _dir_size(p: Path) -> int:
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0

    def privacy_summary(ctx):
        s = settings.all(); data_dir = settings.path.parent; out = settings.output_dir()
        acct = s.get("imap_account")
        return {
            "stored": [
                {"what": "Generated documents (Word, PDF, .eml) and job records", "where": str(out), "bytes": _dir_size(out), "contains_personal_data": True},
                {"what": "Document history (metadata only: template, time, paths, page count)", "where": str(history.path), "bytes": history.path.stat().st_size if history.path.exists() else 0, "contains_personal_data": False, "rows": history.count()},
                {"what": "Settings (output folder, mail server, preferences)", "where": str(settings.path), "bytes": settings.path.stat().st_size if settings.path.exists() else 0, "contains_personal_data": bool(acct)},
                {"what": "Mailbox password", "where": "System keychain (macOS Keychain / Windows Credential Manager)", "bytes": None, "contains_personal_data": True, "present": bool(acct)},
                {"what": "Logs (redacted: no values, no addresses, no secrets)", "where": str(data_dir / "logs"), "bytes": _dir_size(data_dir / "logs"), "contains_personal_data": False},
            ],
            "never_stored": ["form values you type (unless they are printed in the generated document itself)", "email bodies outside the .eml file you choose to save", "any data on a server: there is no Papyra server"],
            "outbound": net.outbound_destinations(s), "offline_mode": bool(s.get("offline_mode")), "keep_history": bool(s.get("keep_history", True)),
            "telemetry": False, "data_dir": str(data_dir),
        }

    def privacy_clear_logs(ctx):
        logs = settings.path.parent / "logs"; n = 0
        for f in logs.glob("backend.log*") if logs.exists() else []:
            try: f.write_text("") if f.name == "backend.log" else f.unlink(); n += 1
            except OSError: pass
        return {"cleared": n}

    def privacy_cleanup(ctx):
        return sweep_temp(0) | sweep_output(settings.output_dir())

    def network_check(ctx):
        sync_offline()
        if imap_draft.OFFLINE["enabled"]:
            raise net.OfflineMode()
        acct = settings.all().get("imap_account")
        if not acct:
            raise EmailAccountMissing()
        return net.check_reachability(acct["host"], int(acct["port"]))

    return {"system.ping": system_ping, "settings.get": settings_get, "settings.set": settings_set,
            "history.list": history_list, "history.delete": history_delete, "history.clear": history_clear,
            "privacy.summary": privacy_summary, "privacy.clear_logs": privacy_clear_logs, "privacy.cleanup": privacy_cleanup,
            "network.check": network_check,
            "email.prepare_eml": email_prepare_eml, "email.imap_get_account": email_imap_get_account,
            "email.imap_test": email_imap_test, "email.imap_save_account": email_imap_save_account,
            "email.imap_remove_account": email_imap_remove_account, "email.create_imap_draft": email_create_imap_draft, "system.shutdown": system_shutdown, "system.diagnostics": system_diagnostics,
            "system.selfcheck": system_selfcheck, "templates.list": templates_list, "templates.rescan": templates_rescan, "templates.example_values": templates_example_values, "docgen.generate": docgen_generate,
            "docgen.convert_pdf": docgen_convert_pdf, "jobs.get": jobs_get}
