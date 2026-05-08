"""
Database module — SQLite tracking for all job applications and follow-ups.
"""

import sqlite3
import os
from datetime import datetime, timedelta
import config


def _verified_to_int(v):
    """SQLite hr_email_verified: 1 Hunter/manual, 0 guessed, NULL unknown (legacy)."""
    if v is True or v == 1:
        return 1
    if v is False or v == 0:
        return 0
    return None


class Database:
    def __init__(self, db_path=None):
        self.db_path = db_path or config.DB_PATH
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Create tables if they don't exist."""
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_title       TEXT NOT NULL,
                    company         TEXT NOT NULL,
                    company_domain  TEXT,
                    platform        TEXT,
                    job_url         TEXT,
                    hr_name         TEXT,
                    hr_email        TEXT,
                    email_status    TEXT DEFAULT 'pending',
                    applied_at      TEXT,
                    follow_up_due   TEXT,
                    follow_up_sent  TEXT,
                    reply_received  INTEGER DEFAULT 0,
                    notes           TEXT,
                    created_at      TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS email_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id      INTEGER REFERENCES jobs(id),
                    email_type  TEXT,   -- 'application' or 'followup'
                    recipient   TEXT,
                    sent_at     TEXT,
                    status      TEXT    -- 'sent' or 'failed'
                );
            """)
            self._migrate_jobs_columns(conn)

    def _migrate_jobs_columns(self, conn):
        """Add optional columns on older DBs."""
        rows = conn.execute("PRAGMA table_info(jobs)").fetchall()
        colnames = {r[1] for r in rows}
        if "search_country" not in colnames:
            conn.execute("ALTER TABLE jobs ADD COLUMN search_country TEXT")
        if "hr_email_verified" not in colnames:
            conn.execute("ALTER TABLE jobs ADD COLUMN hr_email_verified INTEGER")

    # ─── Jobs ──────────────────────────────────────────────────────────────────

    def job_exists(self, company: str, job_title: str) -> bool:
        """Check if we've already tracked this company+title combo."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT id FROM jobs WHERE company=? AND job_title=?",
                (company, job_title)
            ).fetchone()
        return row is not None

    def add_job(self, job: dict, job_title: str) -> int:
        """Insert a new job opportunity. Returns the new row id."""
        with self._get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO jobs
                   (job_title, company, company_domain, platform, job_url, hr_name, hr_email, search_country, hr_email_verified)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    job_title,
                    job.get("company", ""),
                    job.get("domain", ""),
                    job.get("platform", ""),
                    job.get("url", ""),
                    job.get("hr_name", ""),
                    job.get("hr_email", ""),
                    job.get("search_country") or "",
                    _verified_to_int(job.get("hr_email_verified")),
                )
            )
        return cur.lastrowid

    def upsert_job_enrichment(self, job: dict, job_title: str) -> tuple:
        """
        Insert a new row, or update an existing *pending* row with fresh enrichment.
        Rows already marked sent are left unchanged so history stays intact.
        Returns (row_id, 'inserted' | 'updated' | 'unchanged').
        """
        company = job.get("company", "") or ""
        domain = job.get("domain", "") or ""
        platform = job.get("platform", "") or ""
        url = job.get("url", "") or ""
        hr_name = job.get("hr_name", "") or ""
        hr_email = job.get("hr_email", "") or ""
        search_country = job.get("search_country") or ""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT id, email_status FROM jobs WHERE company=? AND job_title=?",
                (company, job_title),
            ).fetchone()
            if row is None:
                v_int = _verified_to_int(job.get("hr_email_verified"))
                cur = conn.execute(
                    """INSERT INTO jobs
                       (job_title, company, company_domain, platform, job_url, hr_name, hr_email, search_country, hr_email_verified)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        job_title,
                        company,
                        domain,
                        platform,
                        url,
                        hr_name,
                        hr_email,
                        search_country,
                        v_int,
                    ),
                )
                return cur.lastrowid, "inserted"
            job_id = row["id"]
            if row["email_status"] != "pending":
                return job_id, "unchanged"
            v_int = _verified_to_int(job.get("hr_email_verified"))
            conn.execute(
                """UPDATE jobs SET company_domain=?, platform=?, job_url=?, hr_name=?, hr_email=?, search_country=?, hr_email_verified=?
                   WHERE id=?""",
                (domain, platform, url, hr_name, hr_email, search_country, v_int, job_id),
            )
            return job_id, "updated"

    def update_email_status(self, job_id: int, status: str):
        """Mark a job as applied and set the follow-up due date."""
        now = datetime.now().isoformat()
        follow_up = (datetime.now() + timedelta(days=config.FOLLOW_UP_DAYS)).date().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE jobs SET email_status=?, applied_at=?, follow_up_due=? WHERE id=?",
                (status, now, follow_up, job_id)
            )

    def update_hr_email(self, job_id: int, hr_email: str, hr_name: str = "", verified: bool = True):
        """Manual adds count as verified by default so SMTP can send when SEND_ONLY_VERIFIED_EMAILS is on."""
        v = 1 if verified else 0
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE jobs SET hr_email=?, hr_name=?, hr_email_verified=? WHERE id=?",
                (hr_email, hr_name, v, job_id),
            )

    def update_hr_by_normalized_job_url(
        self, normalized_url: str, hr_email: str, hr_name: str = "", verified: bool = True
    ) -> int:
        """
        Apply an HR address to all *pending* rows whose job_url normalizes to the same key
        (e.g. after editing the tracking sheet). Returns number of rows updated.
        """
        if not normalized_url or not (hr_email or "").strip():
            return 0
        import job_tracking

        v = 1 if verified else 0
        n = 0
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT id, job_url FROM jobs
                   WHERE email_status = 'pending'
                     AND job_url IS NOT NULL AND length(trim(job_url)) > 0"""
            ).fetchall()
            for r in rows:
                ju = job_tracking.normalize_job_url(r["job_url"] or "")
                if ju == normalized_url:
                    conn.execute(
                        "UPDATE jobs SET hr_email=?, hr_name=?, hr_email_verified=? WHERE id=?",
                        ((hr_email or "").strip(), hr_name or "", v, r["id"]),
                    )
                    n += 1
        return n

    def mark_followup_sent(self, job_id: int):
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE jobs SET follow_up_sent=? WHERE id=?",
                (datetime.now().isoformat(), job_id)
            )

    def mark_replied(self, job_id: int):
        with self._get_conn() as conn:
            conn.execute("UPDATE jobs SET reply_received=1 WHERE id=?", (job_id,))

    def get_sent_job_urls(self) -> list:
        """Normalized URLs that already had an application email marked sent."""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT job_url FROM jobs
                   WHERE email_status = 'sent'
                     AND job_url IS NOT NULL
                     AND length(trim(job_url)) > 0"""
            ).fetchall()
        return [r[0] for r in rows if r[0]]

    def get_pending_applications(self, job_title: str = None) -> list:
        """Jobs with an HR email that haven't been emailed yet. Optionally scoped to one search title."""
        with self._get_conn() as conn:
            if job_title:
                rows = conn.execute(
                    """SELECT * FROM jobs
                       WHERE hr_email IS NOT NULL AND hr_email != ''
                         AND email_status = 'pending'
                         AND job_title = ?
                       ORDER BY id ASC""",
                    (job_title,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM jobs
                       WHERE hr_email IS NOT NULL AND hr_email != ''
                         AND email_status = 'pending'
                       ORDER BY id ASC"""
                ).fetchall()
        return [dict(r) for r in rows]

    def get_pending_followups(self) -> list:
        """Jobs that were applied > N days ago with no follow-up sent yet."""
        today = datetime.now().date().isoformat()
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM jobs
                   WHERE email_status = 'sent'
                     AND follow_up_sent IS NULL
                     AND follow_up_due <= ?
                     AND reply_received = 0
                     AND hr_email IS NOT NULL AND hr_email != ''""",
                (today,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_all_jobs(self, limit: int = 100) -> list:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        with self._get_conn() as conn:
            total       = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            applied     = conn.execute("SELECT COUNT(*) FROM jobs WHERE email_status='sent'").fetchone()[0]
            followed_up = conn.execute("SELECT COUNT(*) FROM jobs WHERE follow_up_sent IS NOT NULL").fetchone()[0]
            pending_fu  = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE email_status='sent' AND follow_up_sent IS NULL"
            ).fetchone()[0]
            replied     = conn.execute("SELECT COUNT(*) FROM jobs WHERE reply_received=1").fetchone()[0]
            no_email    = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE (hr_email IS NULL OR hr_email='') AND email_status='pending'"
            ).fetchone()[0]
        return {
            "total": total,
            "applied": applied,
            "followed_up": followed_up,
            "pending_followup": pending_fu,
            "replied": replied,
            "no_email": no_email,
        }

    # ─── Email Log ──────────────────────────────────────────────────────────────

    def log_email(self, job_id: int, email_type: str, recipient: str, status: str):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO email_log (job_id, email_type, recipient, sent_at, status) VALUES (?,?,?,?,?)",
                (job_id, email_type, recipient, datetime.now().isoformat(), status)
            )
