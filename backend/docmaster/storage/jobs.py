"""Job records: one folder per generation job with a `job.json` describing the outputs.

The record holds paths and content hashes, never the form values (spec §13). The DOCX hash that
the PDF was made from lets us detect an externally edited Word document and refuse to reuse a
stale PDF (spec §8).
"""
from __future__ import annotations
import hashlib, json, re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from ..errors import DocMasterError

JOB_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")     # used with fullmatch: `$` would accept a trailing newline


class JobNotFound(DocMasterError):
    code, rpc_code, user_message = "JOB_NOT_FOUND", -32030, "This document is no longer available."


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_job_id(job_id: str) -> str:
    if not isinstance(job_id, str) or not JOB_ID_RE.fullmatch(job_id):
        raise JobNotFound(data={"job_id": str(job_id)[:80]})
    return job_id


@dataclass
class JobRecord:
    job_id: str
    template_id: str
    template_version: int
    created_at: str
    docx_path: str
    docx_sha256: str
    pdf_path: str | None = None
    pdf_sha256: str | None = None
    pdf_from_docx_sha256: str | None = None   # hash of the DOCX the PDF was converted from
    pages: int | None = None
    expected_pages: dict | None = None
    status: str = "docx_done"                  # docx_done | pdf_done | pdf_failed
    error: dict | None = field(default=None)
    eml_path: str | None = None
    drafts: list = field(default_factory=list)  # {mode, created_at, status, folder|path}

    @staticmethod
    def new(job_id: str, template_id: str, template_version: int, docx: Path, expected_pages: dict | None) -> "JobRecord":
        return JobRecord(job_id, template_id, template_version, datetime.now(timezone.utc).isoformat(timespec="seconds"),
                         str(docx), sha256_of(docx), expected_pages=expected_pages)

    def set_pdf(self, pdf: Path, pages: int) -> None:
        self.pdf_path, self.pdf_sha256, self.pages = str(pdf), sha256_of(pdf), pages
        self.pdf_from_docx_sha256, self.status, self.error = self.docx_sha256, "pdf_done", None

    def current_state(self) -> dict:
        """Re-inspect the files on disk: exists / changed / stale."""
        docx, pdf = Path(self.docx_path), Path(self.pdf_path) if self.pdf_path else None
        docx_exists = docx.exists()
        docx_now = sha256_of(docx) if docx_exists else None
        pdf_exists = bool(pdf and pdf.exists())
        pdf_now = sha256_of(pdf) if pdf_exists else None
        return {
            "docx_exists": docx_exists,
            "docx_changed": docx_exists and docx_now != self.docx_sha256,
            "pdf_exists": pdf_exists,
            "pdf_changed": pdf_exists and pdf_now != self.pdf_sha256,
            # the PDF may only be used if it was made from exactly the DOCX that exists now
            "pdf_stale": not pdf_exists or docx_now != self.pdf_from_docx_sha256 or pdf_now != self.pdf_sha256,
        }


class JobStore:
    """A single job lives in `<output_dir>/<job_id>/job.json`; the documents of a batch share one
    folder and keep their records in `<batch>/.jobs/<job_id>.json`. `jobs-index.json` (ids and
    record paths only) in the data dir remembers where every job is, wherever it was saved."""

    def __init__(self, output_dir: Path, index_path: Path | None = None):
        self.output_dir = output_dir
        self.index_path = index_path
        self._index: dict[str, str] = {}
        if index_path and index_path.exists():
            try: self._index = {k: v for k, v in json.loads(index_path.read_text(encoding="utf8")).items() if isinstance(v, str)}
            except (OSError, ValueError): self._index = {}

    # ---- locations ----
    def default_record(self, job_id: str, base: Path | None = None) -> Path:
        return (base or self.output_dir) / check_job_id(job_id) / "job.json"

    def record_path(self, job_id: str) -> Path:
        check_job_id(job_id)
        v = self._index.get(job_id)
        if v:
            p = Path(v)
            return p if p.suffix == ".json" else p / "job.json"      # older index entries stored the folder
        return self.default_record(job_id)

    def dir(self, job_id: str, base: Path | None = None) -> Path:
        """The folder holding the job's files."""
        if base is not None:
            return base / check_job_id(job_id)
        rec = self.record_path(job_id)
        return rec.parent.parent if rec.parent.name == ".jobs" else rec.parent

    def remember(self, key: str, path: Path) -> None:
        self._index[key] = str(path)
        if self.index_path:
            try:
                self.index_path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.index_path.with_suffix(".tmp"); tmp.write_text(json.dumps(self._index, indent=0), encoding="utf8"); tmp.replace(self.index_path)
            except OSError:
                pass

    # ---- records ----
    def save(self, rec: JobRecord, base: Path | None = None, record_path: Path | None = None) -> None:
        p = record_path or (self.default_record(rec.job_id, base) if base is not None else self.record_path(rec.job_id))
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(rec), indent=1), encoding="utf8")
        tmp.replace(p)
        self.remember(rec.job_id, p)

    def load(self, job_id: str) -> JobRecord:
        p = self.record_path(job_id)
        if not p.exists():
            p = self.default_record(job_id)                       # indexed location gone: default place
        if not p.exists():
            raise JobNotFound(data={"job_id": job_id})
        try:
            return JobRecord(**json.loads(p.read_text(encoding="utf8")))
        except (ValueError, TypeError) as e:
            raise JobNotFound(f"job record unreadable: {e}", data={"job_id": job_id})

    # ---- batches ----
    def save_batch(self, batch: dict) -> Path:
        d = Path(batch["dir"]); d.mkdir(parents=True, exist_ok=True)
        p = d / "batch.json"; tmp = d / "batch.json.tmp"
        tmp.write_text(json.dumps(batch, indent=1), encoding="utf8"); tmp.replace(p)
        self.remember(f"batch:{check_job_id(batch['batch_id'])}", p)
        return p

    def load_batch(self, batch_id: str) -> dict:
        v = self._index.get(f"batch:{check_job_id(batch_id)}")
        p = Path(v) if v else None
        if p is None or not p.exists():
            raise JobNotFound(data={"batch_id": batch_id})
        try:
            return json.loads(p.read_text(encoding="utf8"))
        except ValueError as e:
            raise JobNotFound(f"batch record unreadable: {e}", data={"batch_id": batch_id})
