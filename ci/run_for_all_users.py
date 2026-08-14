"""
Daily CI runner — executes the job search + score pipeline for every user
who has an active resume profile in Supabase.

Run with:  python ci/run_for_all_users.py
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import date
from pathlib import Path

# Make project root importable when running from repo root or ci/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(override=True)

from supabase_client import get_admin_supabase
from job_searcher import search_and_store_jobs, score_jobs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def fetch_all_users_with_resumes() -> list[dict]:
    """Return list of {user_id, parsed_profile} for every user with a primary resume."""
    db = get_admin_supabase()
    res = (
        db.table("resume_profiles")
        .select("user_id, parsed_profile")
        .eq("is_primary", True)
        .execute()
    )
    return res.data or []


def run():
    today = date.today().isoformat()
    users = fetch_all_users_with_resumes()
    logger.info("Found %d user(s) with active resumes — starting daily run for %s", len(users), today)

    if not users:
        logger.warning("No users found — nothing to do.")
        return

    total_found = 0
    total_scored = 0

    for entry in users:
        uid = entry["user_id"]
        profile = entry.get("parsed_profile") or {}
        logger.info("── User %s ──────────────────────────", uid[:8])

        try:
            found = search_and_store_jobs(profile, user_id=uid)
            logger.info("  Stored %d new jobs", found)
            total_found += found
        except Exception as exc:
            logger.error("  search_and_store_jobs failed: %s", exc)
            continue

        try:
            scored = score_jobs(profile, today, user_id=uid)
            logger.info("  Scored %d jobs", scored)
            total_scored += scored
        except Exception as exc:
            logger.error("  score_jobs failed: %s", exc)

    logger.info("Done. Total new jobs: %d | Total scored: %d", total_found, total_scored)


if __name__ == "__main__":
    run()
