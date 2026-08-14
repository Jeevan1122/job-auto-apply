from __future__ import annotations

import sqlite3
import json
from datetime import date, datetime
from typing import List, Optional
from contextlib import contextmanager

from config import DB_PATH


# ── Connection ────────────────────────────────────────────────────────────────

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ── Schema ────────────────────────────────────────────────────────────────────

def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS resume_profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            raw_text TEXT NOT NULL,
            parsed_profile_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            location TEXT,
            url TEXT UNIQUE NOT NULL,
            source TEXT NOT NULL,
            description TEXT,
            job_type TEXT,
            relevance_score REAL DEFAULT 0.0,
            relevance_reason TEXT,
            status TEXT NOT NULL DEFAULT 'found',
            applied_at TEXT,
            found_at TEXT NOT NULL DEFAULT (datetime('now')),
            date TEXT NOT NULL,
            notes TEXT,
            manually_applied INTEGER DEFAULT 0,
            resume_filename TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS daily_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE NOT NULL,
            jobs_found INTEGER DEFAULT 0,
            jobs_applied INTEGER DEFAULT 0,
            jobs_failed INTEGER DEFAULT 0,
            jobs_manual INTEGER DEFAULT 0,
            jobs_skipped INTEGER DEFAULT 0,
            top_companies TEXT,
            sheets_updated INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)
        # Migrate existing databases that lack new columns
        for table, col, defn in [
            ("jobs",           "manually_applied", "INTEGER DEFAULT 0"),
            ("jobs",           "resume_filename",  "TEXT DEFAULT ''"),
            ("resume_profile", "is_primary",       "INTEGER DEFAULT 0"),
        ]:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {defn}")
            except Exception:
                pass


# ── Resume profile ─────────────────────────────────────────────────────────────

def save_resume_profile(filename: str, raw_text: str, parsed_profile: dict) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO resume_profile (filename, raw_text, parsed_profile_json) VALUES (?,?,?)",
            (filename, raw_text, json.dumps(parsed_profile))
        )
        return cur.lastrowid


def get_latest_resume_profile() -> Optional[dict]:
    """Returns the primary resume if one is starred, else the most recently uploaded."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM resume_profile ORDER BY is_primary DESC, created_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["parsed_profile"] = json.loads(d["parsed_profile_json"])
    return d


def get_all_resume_profiles() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, filename, created_at, is_primary FROM resume_profile ORDER BY is_primary DESC, created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def set_primary_resume(resume_id: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE resume_profile SET is_primary=0")
        conn.execute("UPDATE resume_profile SET is_primary=1 WHERE id=?", (resume_id,))


def delete_resume_profile(resume_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM resume_profile WHERE id=?", (resume_id,))


# ── Jobs ───────────────────────────────────────────────────────────────────────

def upsert_job(job: dict) -> bool:
    """Returns True if a new job was inserted, False if it already existed."""
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM jobs WHERE url = ? OR job_id = ?",
            (job["url"], job["job_id"])
        ).fetchone()
        if existing:
            return False
        conn.execute("""
            INSERT INTO jobs
              (job_id, title, company, location, url, source, description, job_type, date)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            job["job_id"], job["title"], job["company"],
            job.get("location", ""), job["url"], job["source"],
            job.get("description", ""), job.get("job_type", ""),
            date.today().isoformat()
        ))
        return True


def update_job_score(job_id: str, score: float, reason: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE jobs SET relevance_score=?, relevance_reason=?, status='scored' WHERE job_id=?",
            (score, reason, job_id)
        )


def update_job_status(job_id: str, status: str, notes: str = ""):
    applied_at = datetime.now().isoformat() if status == "applied" else None
    with get_conn() as conn:
        conn.execute(
            "UPDATE jobs SET status=?, notes=?, applied_at=? WHERE job_id=?",
            (status, notes, applied_at, job_id)
        )


def mark_manually_applied(job_id: str, resume_filename: str = "") -> None:
    applied_at = datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute(
            "UPDATE jobs SET manually_applied=1, resume_filename=?, applied_at=? WHERE job_id=?",
            (resume_filename.strip(), applied_at, job_id)
        )


def unmark_manually_applied(job_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE jobs SET manually_applied=0, resume_filename='', applied_at=NULL WHERE job_id=?",
            (job_id,)
        )


def get_manually_applied_jobs() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE manually_applied=1 ORDER BY applied_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_jobs_for_scoring(today: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE date=? AND status='found'",
            (today,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_jobs_to_apply(today: str, min_score: float) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM jobs
            WHERE date=? AND status='scored' AND relevance_score >= ?
            ORDER BY relevance_score DESC
        """, (today, min_score)).fetchall()
    return [dict(r) for r in rows]


def get_all_jobs(limit: int = 500) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY found_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_today_stats(today: str) -> dict:
    with get_conn() as conn:
        row = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN manually_applied=1 THEN 1 ELSE 0 END) as applied,
                SUM(CASE WHEN manually_applied=0 AND relevance_score >= 0.65 THEN 1 ELSE 0 END) as pending,
                AVG(CASE WHEN relevance_score > 0 THEN relevance_score END) as avg_score
            FROM jobs WHERE date=?
        """, (today,)).fetchone()
    return dict(row) if row else {}


def reset_today_statuses(today: str) -> None:
    """Clear old auto-apply statuses so sidebar stats start fresh."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE jobs SET status='scored', manually_applied=0, resume_filename='', applied_at=NULL WHERE date=?",
            (today,)
        )


# ── Daily summary ──────────────────────────────────────────────────────────────

def upsert_daily_summary(
    today: str,
    jobs_found: int,
    jobs_applied: int,
    jobs_failed: int,
    jobs_manual: int,
    jobs_skipped: int,
    top_companies: list[str],
    sheets_updated: bool
):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO daily_summary
              (date, jobs_found, jobs_applied, jobs_failed, jobs_manual, jobs_skipped,
               top_companies, sheets_updated)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(date) DO UPDATE SET
              jobs_found=excluded.jobs_found,
              jobs_applied=excluded.jobs_applied,
              jobs_failed=excluded.jobs_failed,
              jobs_manual=excluded.jobs_manual,
              jobs_skipped=excluded.jobs_skipped,
              top_companies=excluded.top_companies,
              sheets_updated=excluded.sheets_updated
        """, (
            today, jobs_found, jobs_applied, jobs_failed,
            jobs_manual, jobs_skipped,
            json.dumps(top_companies), int(sheets_updated)
        ))


def get_all_daily_summaries() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_summary ORDER BY date DESC"
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["top_companies"] = json.loads(d.get("top_companies") or "[]")
        except Exception:
            d["top_companies"] = []
        result.append(d)
    return result
