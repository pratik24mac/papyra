"""Local document history in SQLite (one file in the app data dir).

Stores metadata only: which template, when, where the files are, page count, draft outcomes.
Never form values, never email bodies, never credentials. Rows can be deleted individually or
all at once, optionally together with the files on disk.
"""
from __future__ import annotations
import shutil, sqlite3, threading
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (
  job_id TEXT PRIMARY KEY,
  template_id TEXT NOT NULL,
  template_version INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL,
  output_dir TEXT NOT NULL,
  docx_path TEXT,
  pdf_path TEXT,
  pages INTEGER,
  error_code TEXT
);
CREATE TABLE IF NOT EXISTS drafts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
  mode TEXT NOT NULL,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL,
  location TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class History:
    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / "history.db"
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL"); self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        if self._conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 0:
            self._conn.execute("INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION,))

    # ---- writes ----
    def record_job(self, job_id, template_id, template_version, status, output_dir, docx_path=None, pdf_path=None, pages=None, error_code=None):
        with self._lock:
            self._conn.execute("""INSERT INTO jobs(job_id, template_id, template_version, created_at, status, output_dir, docx_path, pdf_path, pages, error_code)
                VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET status=excluded.status, docx_path=excluded.docx_path,
                pdf_path=excluded.pdf_path, pages=excluded.pages, error_code=excluded.error_code""",
                (job_id, template_id, template_version, _now(), status, str(output_dir), docx_path and str(docx_path), pdf_path and str(pdf_path), pages, error_code))

    def record_draft(self, job_id, mode, status, location=None) -> bool:
        """Returns False when the job is not in the history (history was off when it was generated)."""
        with self._lock:
            if not self._conn.execute("SELECT 1 FROM jobs WHERE job_id=?", (job_id,)).fetchone():
                return False
            self._conn.execute("INSERT INTO drafts(job_id, mode, created_at, status, location) VALUES(?,?,?,?,?)", (job_id, mode, _now(), status, location))
            return True

    # ---- reads ----
    def list(self, limit: int = 50, offset: int = 0) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("""SELECT j.*, (SELECT COUNT(*) FROM drafts d WHERE d.job_id=j.job_id) AS drafts
                FROM jobs j ORDER BY created_at DESC LIMIT ? OFFSET ?""", (max(1, min(limit, 500)), max(0, offset))).fetchall()
            cols = [c[0] for c in self._conn.execute("SELECT * FROM jobs LIMIT 0").description] + ["drafts"]
        out = []
        for r in rows:
            d = dict(zip(cols, r))
            d["docx_exists"] = bool(d["docx_path"] and Path(d["docx_path"]).exists())
            d["pdf_exists"] = bool(d["pdf_path"] and Path(d["pdf_path"]).exists())
            out.append(d)
        return out

    def count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    def job_dir(self, job_id: str) -> Path | None:
        with self._lock:
            r = self._conn.execute("SELECT output_dir FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return Path(r[0]) / job_id if r else None

    # ---- deletes ----
    def delete(self, job_id: str, delete_files: bool) -> dict:
        d = self.job_dir(job_id)
        removed_files = False
        if delete_files and d and d.exists() and d.is_dir() and d.name == job_id:
            shutil.rmtree(d, ignore_errors=True); removed_files = not d.exists()
        with self._lock:
            n = self._conn.execute("DELETE FROM jobs WHERE job_id=?", (job_id,)).rowcount
        return {"job_id": job_id, "removed_row": n > 0, "removed_files": removed_files}

    def clear(self, delete_files: bool) -> dict:
        rows = self.list(limit=500)
        removed = 0
        for r in rows:
            if self.delete(r["job_id"], delete_files)["removed_files"]:
                removed += 1
        with self._lock:
            self._conn.execute("DELETE FROM drafts"); self._conn.execute("DELETE FROM jobs"); self._conn.execute("VACUUM")
        return {"removed_rows": len(rows), "removed_job_folders": removed}

    def close(self):
        self._conn.close()
