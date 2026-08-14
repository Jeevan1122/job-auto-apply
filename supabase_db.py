"""
Per-user database operations using Supabase.
All functions require a user_id so data is always isolated per user.
Uses the service-role client (bypasses RLS) with manual user_id filtering.
"""
from __future__ import annotations

from datetime import date
from supabase_client import get_admin_supabase


# ── Resume profiles ────────────────────────────────────────────────────────────

def save_resume_profile(user_id: str, filename: str, raw_text: str, parsed: dict) -> str:
    db = get_admin_supabase()
    # Clear existing primary flag for this user
    db.table("resume_profiles") \
      .update({"is_primary": False}) \
      .eq("user_id", user_id) \
      .execute()
    # Insert new profile as primary
    res = db.table("resume_profiles").insert({
        "user_id":        user_id,
        "filename":       filename,
        "raw_text":       raw_text,
        "parsed_profile": parsed,
        "is_primary":     True,
    }).execute()
    return res.data[0]["id"]


def get_latest_resume_profile(user_id: str) -> dict | None:
    db = get_admin_supabase()
    res = db.table("resume_profiles") \
            .select("*") \
            .eq("user_id", user_id) \
            .eq("is_primary", True) \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()
    if not res.data:
        return None
    row = res.data[0]
    return {
        "id":             row["id"],
        "filename":       row["filename"],
        "raw_text":       row.get("raw_text", ""),
        "parsed_profile": row.get("parsed_profile", {}),
        "is_primary":     row.get("is_primary", True),
        "created_at":     row.get("created_at", ""),
    }


def get_all_resume_profiles(user_id: str) -> list[dict]:
    db = get_admin_supabase()
    res = db.table("resume_profiles") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("created_at", desc=True) \
            .execute()
    return res.data or []


def set_primary_resume(user_id: str, profile_id: str):
    db = get_admin_supabase()
    db.table("resume_profiles") \
      .update({"is_primary": False}) \
      .eq("user_id", user_id) \
      .execute()
    db.table("resume_profiles") \
      .update({"is_primary": True}) \
      .eq("id", profile_id) \
      .eq("user_id", user_id) \
      .execute()


def delete_resume_profile(user_id: str, profile_id: str):
    db = get_admin_supabase()
    db.table("resume_profiles") \
      .delete() \
      .eq("id", profile_id) \
      .eq("user_id", user_id) \
      .execute()


# ── Jobs ───────────────────────────────────────────────────────────────────────

def get_all_jobs(user_id: str, target_date: str | None = None) -> list[dict]:
    db = get_admin_supabase()
    q = db.table("jobs").select("*").eq("user_id", user_id)
    if target_date:
        q = q.eq("date", target_date)
    res = q.order("relevance_score", desc=True).execute()
    return res.data or []


def get_today_stats(user_id: str, today: str) -> dict:
    jobs = get_all_jobs(user_id, today)
    applied = [j for j in jobs if j.get("status") == "applied"]
    return {
        "total":   len(jobs),
        "applied": len(applied),
        "new":     len([j for j in jobs if j.get("status") == "new"]),
    }


def update_job_status(user_id: str, job_id: str, status: str):
    db = get_admin_supabase()
    db.table("jobs") \
      .update({"status": status}) \
      .eq("job_id", job_id) \
      .eq("user_id", user_id) \
      .execute()


def get_all_daily_summaries(user_id: str) -> list[dict]:
    db = get_admin_supabase()
    res = db.table("daily_summary") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("date", desc=True) \
            .execute()
    return res.data or []


def upsert_daily_summary(user_id: str, today: str, jobs_found: int, jobs_applied: int):
    db = get_admin_supabase()
    db.table("daily_summary").upsert({
        "user_id":      user_id,
        "date":         today,
        "jobs_found":   jobs_found,
        "jobs_applied": jobs_applied,
    }, on_conflict="user_id,date").execute()


def upsert_job(user_id: str, job: dict) -> bool:
    """Insert job for this user. Returns True if new, False if duplicate."""
    db = get_admin_supabase()
    try:
        db.table("jobs").insert({
            "user_id":         user_id,
            "job_id":          job["job_id"],
            "title":           job.get("title", ""),
            "company":         job.get("company", ""),
            "location":        job.get("location", ""),
            "url":             job.get("url", ""),
            "source":          job.get("source", ""),
            "description":     job.get("description", "")[:2000],
            "job_type":        job.get("job_type", "fulltime"),
            "relevance_score": job.get("relevance_score", 0),
            "score_reason":    job.get("score_reason", ""),
            "status":          "new",
            "date":            date.today().isoformat(),
        }).execute()
        return True
    except Exception:
        return False  # duplicate (unique constraint on user_id + job_id)
