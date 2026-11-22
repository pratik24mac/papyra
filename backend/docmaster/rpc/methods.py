"""The closed list of RPC methods. Each maps 1:1 to a Tauri command."""
from __future__ import annotations
import os, platform, sys, time, uuid
from pathlib import Path
from .. import __version__
from ..docgen.ooxml import set_document_properties
from ..docgen.render import render_docx, validate, normalise_values
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
from ..errors import EmailAccountMissing, PdfStale, OutputPathError, DocMasterError, ValidationError
from datetime import datetime, timezone
from ..errors import PdfConversionFailed, PdfInvalid
from docx import Document
from ..pdfconv import libreoffice
from ..pdfconv.libreoffice import convert_to_pdf, find_soffice, soffice_version, validate_pdf
from ..pdfconv import watermark as watermark_mod
from ..pdfconv.watermark import apply_watermark, config_from_schema
from ..storage.paths import ensure_dir, filename_from_pattern, unique_path
from ..templates.catalogue import Catalogue


def build_methods(templates_dir: Path, output_dir: Path, soffice_override: str | None = None, data_dir: Path | None = None,
                  credentials: CredentialStore | None = None, imap_factory=None, user_templates_dir: Path | None = None) -> dict:
    user_templates_dir = user_templates_dir or output_dir / "templates"
    try: Catalogue.ensure_user_root(user_templates_dir)
    except OSError: pass
    catalogue = Catalogue(templates_dir, user_templates_dir)
    settings = Settings(data_dir or output_dir.parent / ".papyra", output_dir)
    jobs = JobStore(settings.output_dir(), settings.path.parent / "jobs-index.json")   # default re-pointed on every call via current_jobs()
    creds = credentials or CredentialStore()
    history = History(settings.path.parent)
    # persistent LibreOffice profile: first-start cost once per installation, warmed in the background
    libreoffice.configure(settings.path.parent / "lo-profile")
    watermark_mod.configure(settings.path.parent / "watermark-cache")
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

    def _target_dir(output_dir: str | None) -> Path:
        """Per-document folder override ("Save to"): absolute, created, remembered as the last choice."""
        if not output_dir:
            return settings.output_dir()
        p = Path(os.path.expanduser(str(output_dir)))
        if not p.is_absolute():
            raise OutputPathError(data={"path": str(p), "reason": "the save folder must be an absolute path"})
        ensure_dir(p)
        settings.set("last_output_dir", str(p.resolve()))
        return p.resolve()

    def _generate_document(ctx, tpl, values: dict, job_id: str, out_dir: Path, base_dir: Path, record_path: Path | None = None,
                           batch: dict | None = None, progress_extra: dict | None = None):
        """One document into `out_dir` (its own job folder, or the shared batch folder)."""
        extra = progress_extra or {}
        meta = tpl.schema["template"]; template_id = tpl.id
        keep = settings.all().get("keep_history", True)
        hist_batch = {"batch_id": batch["batch_id"], "batch_dir": batch["dir"]} if batch else {}
        stem = filename_from_pattern(meta.get("output_filename", "{date}-" + template_id), values)
        docx_path = unique_path(out_dir, stem, ".docx")
        ctx.progress(job_id=job_id, stage="rendering_docx", message="Generating Word document", **extra)
        render_docx(tpl.docx, tpl.schema, values, docx_path, default_date_format=settings.all().get("date_format"))
        d = Document(docx_path); set_document_properties(d, f"{meta['name']} — {stem}", subject=meta["name"]); d.save(docx_path)
        rec = JobRecord.new(job_id, template_id, tpl.version, docx_path, meta.get("expected_pages"))
        current_jobs().save(rec, base_dir if record_path is None else None, record_path)
        if keep: history.record_job(job_id, template_id, tpl.version, "docx_done", base_dir, docx_path, template_name=meta.get("name"), **hist_batch)
        ctx.progress(job_id=job_id, stage="docx_done", message="Word document created", docx_path=str(docx_path), **extra)
        ctx.progress(job_id=job_id, stage="converting_pdf", message="Converting to PDF" if libreoffice.profile_is_warm()
                     else "Starting LibreOffice for the first time on this computer; this can take a few minutes once", **extra)
        try:
            pdf_path, seconds = convert_to_pdf(docx_path, find_soffice(soffice_override))
            wm = config_from_schema(tpl.schema, tpl.dir)
            if wm: apply_watermark(pdf_path, wm)
            pages = validate_pdf(pdf_path, meta.get("expected_pages"),
                                 [str(values.get(k, "")) for k in meta.get("essential_text", [])])
        except (PdfConversionFailed, PdfInvalid) as e:
            e.data.setdefault("docx_path", str(docx_path)); e.data["job_id"] = job_id
            rec.status, rec.error = "pdf_failed", {"code": e.code, "message": str(e)}; current_jobs().save(rec)
            if keep: history.record_job(job_id, template_id, tpl.version, "pdf_failed", base_dir, docx_path, error_code=e.code, template_name=meta.get("name"), **hist_batch)
            raise
        rec.set_pdf(pdf_path, pages); current_jobs().save(rec)
        if keep: history.record_job(job_id, template_id, tpl.version, "pdf_done", base_dir, docx_path, pdf_path, pages, template_name=meta.get("name"), **hist_batch)
        ctx.progress(job_id=job_id, stage="pdf_done", message=f"PDF created ({pages} pages)", pdf_path=str(pdf_path), **extra)
        return {"job_id": job_id, "template_id": template_id, "template_version": tpl.version, "template_name": meta.get("name"),
                "docx_path": str(docx_path), "pdf_path": str(pdf_path), "pages": pages,
                "docx_sha256": rec.docx_sha256, "pdf_sha256": rec.pdf_sha256, "pdf_seconds": round(seconds, 2)}

    def docgen_generate(ctx, template_id: str, values: dict, job_id: str | None = None, output_dir: str | None = None):
        job_id = job_id or uuid.uuid4().hex
        t0 = time.monotonic()
        tpl = catalogue.get(template_id)
        ctx.progress(job_id=job_id, stage="validating", message="Checking values")
        values = normalise_values(tpl.schema, values) if isinstance(values, dict) else values
        validate(tpl.schema, values)                     # fail before anything touches the disk
        base_dir = _target_dir(output_dir)
        out_dir = ensure_dir(base_dir / job_id)
        result = _generate_document(ctx, tpl, values, job_id, out_dir, base_dir)
        return result | {"total_ms": int((time.monotonic() - t0) * 1000)}

    PERSON_KEYS = ("full_name", "employee_name", "client_name", "name", "company_name")

    def docgen_generate_batch(ctx, templates: list, values: dict, values_by_template: dict | None = None,
                              batch_id: str | None = None, output_dir: str | None = None):
        """Every selected template from one set of values, into one folder per batch.
        A failing document does not stop the others; the result lists each document's status."""
        if not templates or not isinstance(templates, list):
            raise ValidationError("choose at least one template", data={"errors": ["templates: empty"]})
        batch_id = batch_id or uuid.uuid4().hex
        t0 = time.monotonic()
        tpls = [catalogue.get(str(t)) for t in templates]
        per = values_by_template or {}
        if not isinstance(values, dict):
            raise ValidationError(data={"errors": ["values: expected an object"]})
        merged = {t.id: normalise_values(t.schema, {**values, **(per.get(t.id) or {})}) for t in tpls}
        ctx.progress(job_id=batch_id, stage="validating", message=f"Checking values for {len(tpls)} documents")
        for t in tpls:
            try: validate(t.schema, merged[t.id])
            except ValidationError as e:
                e.data["template_id"] = t.id; e.data["template_name"] = t.schema["template"].get("name"); raise
        base_dir = _target_dir(output_dir)
        person = next((str(values.get(k)).strip() for k in PERSON_KEYS if str(values.get(k) or "").strip()), "") or batch_id[:8]
        from ..storage.paths import safe_stem
        from datetime import date as _date
        stem = safe_stem(f"{person}-{_date.today().isoformat()}")
        batch_dir = base_dir / stem; n = 2
        while batch_dir.exists():
            batch_dir = base_dir / f"{stem} ({n})"; n += 1
        ensure_dir(batch_dir); ensure_dir(batch_dir / ".jobs")
        batch = {"batch_id": batch_id, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "dir": str(batch_dir),
                 "person": person, "documents": []}
        current_jobs().save_batch(batch)
        docs = []
        for i, t in enumerate(tpls):
            job_id = uuid.uuid4().hex
            extra = {"batch_id": batch_id, "document": t.id, "document_name": t.schema["template"].get("name"), "index": i, "total": len(tpls), "doc_job_id": job_id}
            try:
                r = _generate_document(ctx, t, merged[t.id], job_id, batch_dir, base_dir, batch_dir / ".jobs" / f"{job_id}.json", batch, extra)
                docs.append({**r, "status": "pdf_done"})
            except DocMasterError as e:
                log.warning("batch %s: %s failed: %s %s", batch_id, t.id, e.code, e)
                docs.append({"job_id": job_id, "template_id": t.id, "template_name": t.schema["template"].get("name"), "status": "failed",
                             "docx_path": e.data.get("docx_path"), "pdf_path": None, "pages": None, "error": {"code": e.code, "message": str(e), "data": e.data}})
                ctx.progress(job_id=job_id, stage="failed", message=f"{t.schema['template'].get('name')}: {e}", **extra)
        batch["documents"] = docs; current_jobs().save_batch(batch)
        ok = all(d["status"] == "pdf_done" for d in docs)
        ctx.progress(job_id=batch_id, stage="batch_done", message=f"{sum(d['status'] == 'pdf_done' for d in docs)} of {len(docs)} documents ready")
        return {"batch_id": batch_id, "batch_dir": str(batch_dir), "person": person, "ok": ok, "documents": docs,
                "total_ms": int((time.monotonic() - t0) * 1000)}

    def batches_get(ctx, batch_id: str):
        batch = current_jobs().load_batch(batch_id)
        for d in batch.get("documents", []):
            if d.get("status") == "pdf_done":
                try: d["state"] = current_jobs().load(d["job_id"]).current_state()
                except DocMasterError: d["state"] = {"pdf_stale": True, "pdf_exists": False, "docx_exists": False, "docx_changed": False, "pdf_changed": False}
        return batch

    def jobs_get(ctx, job_id: str):
        """Current state of a job's files: used before preview/email to refuse a stale PDF."""
        rec = current_jobs().load(job_id)
        return {"job": rec.__dict__, "state": rec.current_state(), "output_dir": str(Path(rec.docx_path).parent.parent)}

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
            try:
                t = catalogue.get(rec.template_id); wm = config_from_schema(t.schema, t.dir)
            except Exception: wm = None  # noqa: BLE001  (template no longer available: convert without watermark)
            if wm: apply_watermark(pdf_path, wm)
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

    def settings_payload():
        from ..docgen.dates import PRESETS, format_date
        return settings.all() | {"date_format_presets": [{"format": p, "example": format_date("2026-03-12", p)} for p in PRESETS],
                                 "date_format_example": format_date("2026-03-12", settings.all().get("date_format") or "D MMMM YYYY")}

    def settings_get(ctx):
        return settings_payload()

    def settings_set(ctx, key: str, value=None):
        settings.set(key, value)
        return settings_payload()

    # ---------------- email ----------------
    def _fresh_pdf_job(job_id: str):
        rec = current_jobs().load(job_id)
        st = rec.current_state()
        if st["pdf_stale"]:
            raise PdfStale(data={"job_id": job_id})
        return rec

    def _record_draft(rec, entry: dict):
        rec.drafts.append({"created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}); current_jobs().save(rec)

    def _jobs_for(job_id, job_ids):
        ids = [j for j in (job_ids or []) if j] or ([job_id] if job_id else [])
        if not ids:
            raise ValidationError("no document selected", data={"errors": ["job_id: required"]})
        return [_fresh_pdf_job(j) for j in ids]

    def email_prepare_eml(ctx, message: dict, job_id: str | None = None, job_ids: list | None = None):
        recs = _jobs_for(job_id, job_ids); rec = recs[0]
        acct = settings.all().get("imap_account")
        spec = DraftSpec.from_dict(message, sender=(acct or {}).get("email"))
        path = write_eml(spec, [Path(r.pdf_path) for r in recs])
        for r in recs:
            r.eml_path = str(path); _record_draft(r, {"mode": "eml", "status": "saved", "path": str(path)})
        if settings.all().get("keep_history", True):
            for r in recs: history.record_draft(r.job_id, "eml", "saved", str(path))
        return {"job_id": rec.job_id, "job_ids": [r.job_id for r in recs], "eml_path": str(path), "bytes": path.stat().st_size,
                "attachment": Path(rec.pdf_path).name, "attachments": [Path(r.pdf_path).name for r in recs]}

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

    def email_create_imap_draft(ctx, message: dict, job_id: str | None = None, job_ids: list | None = None):
        sync_offline()
        acct_d = settings.all().get("imap_account")
        if not acct_d:
            raise EmailAccountMissing()
        acct = imap_draft.ImapAccount.from_dict(acct_d)
        pw = creds.get(f"imap:{acct.email}")
        if pw is None:
            raise EmailAccountMissing("the mailbox password is missing from the credential store")
        recs = _jobs_for(job_id, job_ids); rec = recs[0]
        spec = DraftSpec.from_dict(message, sender=acct.email)
        from ..email.mime import build_message
        ctx.progress(job_id=rec.job_id, stage="email_connecting", message=f"Connecting to {acct.host}")
        res = imap_draft.append_draft(acct, pw, build_message(spec, [Path(r.pdf_path) for r in recs]), factory=imap_factory)
        for r in recs:
            _record_draft(r, {"mode": "imap", "status": "saved", "folder": res["folder"], "uid": res.get("uid"), "account": acct.email})
            if settings.all().get("keep_history", True): history.record_draft(r.job_id, "imap", "saved", res["folder"])
        return {"job_id": rec.job_id, "job_ids": [r.job_id for r in recs], "account": acct.email, **res,
                "attachment": Path(rec.pdf_path).name, "attachments": [Path(r.pdf_path).name for r in recs]}

    # ---------------- history / privacy / network ----------------
    def history_list(ctx, limit: int = 50, offset: int = 0):
        return {"jobs": history.list_grouped(limit, offset), "total": history.count()}

    def history_delete_batch(ctx, batch_id: str, delete_files: bool = False):
        from ..storage.jobs import check_job_id
        return history.delete_batch(check_job_id(batch_id), bool(delete_files))

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
            "history.list": history_list, "history.delete": history_delete, "history.delete_batch": history_delete_batch, "history.clear": history_clear,
            "privacy.summary": privacy_summary, "privacy.clear_logs": privacy_clear_logs, "privacy.cleanup": privacy_cleanup,
            "network.check": network_check,
            "email.prepare_eml": email_prepare_eml, "email.imap_get_account": email_imap_get_account,
            "email.imap_test": email_imap_test, "email.imap_save_account": email_imap_save_account,
            "email.imap_remove_account": email_imap_remove_account, "email.create_imap_draft": email_create_imap_draft, "system.shutdown": system_shutdown, "system.diagnostics": system_diagnostics,
            "system.selfcheck": system_selfcheck, "templates.list": templates_list, "templates.rescan": templates_rescan, "templates.example_values": templates_example_values, "docgen.generate": docgen_generate, "docgen.generate_batch": docgen_generate_batch, "batches.get": batches_get,
            "docgen.convert_pdf": docgen_convert_pdf, "jobs.get": jobs_get}
