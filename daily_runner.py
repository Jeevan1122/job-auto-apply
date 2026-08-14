"""
Daily pipeline (search + score + report only — no auto-apply):
  1. Search jobs across LinkedIn, Indeed, Greenhouse, Glassdoor, Dice, Monster
  2. Score relevance with AI against your resume
  3. Generate Excel + PDF reports on Desktop
  4. Sync to Google Sheets (optional)
"""
from __future__ import annotations

import logging
import sys
from datetime import date

from database import (
    init_db, get_latest_resume_profile,
    upsert_daily_summary, get_today_stats,
)
from job_searcher import search_and_store_jobs, score_jobs
from excel_reporter import export_excel
from pdf_reporter import export_pdf
from sheets_updater import sync_to_sheets
from config import MAX_JOBS_PER_RUN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run_pipeline(resume_path: str = None) -> dict:
    init_db()
    today = date.today().isoformat()
    logger.info("═══ Daily pipeline started — %s ═══", today)

    # ── 1. Load resume profile ─────────────────────────────────────────────────
    profile_row = get_latest_resume_profile()
    if not profile_row:
        logger.error("No resume profile found. Upload a resume via the UI first.")
        return {"error": "no_resume_profile"}

    profile = profile_row["parsed_profile"]
    logger.info("Profile loaded: %s", profile.get("current_title", "unknown"))

    # ── 2. Search jobs ─────────────────────────────────────────────────────────
    logger.info("Searching jobs across all boards...")
    new_jobs = search_and_store_jobs(profile, max_jobs=MAX_JOBS_PER_RUN)
    logger.info("Found %d new jobs", new_jobs)

    # ── 3. Score relevance ─────────────────────────────────────────────────────
    logger.info("Scoring relevance with AI...")
    scored = score_jobs(profile, today)
    logger.info("Scored %d jobs", scored)

    # ── 4. Save daily summary ──────────────────────────────────────────────────
    stats = get_today_stats(today)
    upsert_daily_summary(
        today          = today,
        jobs_found     = stats.get("total", 0),
        jobs_applied   = 0,
        jobs_failed    = 0,
        jobs_manual    = 0,
        jobs_skipped   = 0,
        top_companies  = [],
        sheets_updated = False,
    )

    # ── 5. Excel + PDF reports ─────────────────────────────────────────────────
    excel_path = ""
    pdf_path   = ""
    try:
        excel_path = export_excel(today)
        logger.info("Excel saved: %s", excel_path)
    except Exception as e:
        logger.error("Excel export failed: %s", e)

    try:
        pdf_path = export_pdf(today)
        logger.info("PDF saved: %s", pdf_path)
    except Exception as e:
        logger.error("PDF export failed: %s", e)

    # ── 6. Google Sheets sync (optional) ──────────────────────────────────────
    sheets_ok = sync_to_sheets()

    upsert_daily_summary(
        today          = today,
        jobs_found     = stats.get("total", 0),
        jobs_applied   = 0,
        jobs_failed    = 0,
        jobs_manual    = 0,
        jobs_skipped   = 0,
        top_companies  = [],
        sheets_updated = sheets_ok,
    )

    summary = {
        "date":          today,
        "jobs_found":    new_jobs,
        "jobs_scored":   scored,
        "excel_path":    excel_path,
        "pdf_path":      pdf_path,
        "sheets_updated": sheets_ok,
    }
    logger.info("═══ Pipeline complete: %s ═══", summary)
    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-now", action="store_true", help="Run pipeline immediately")
    args = parser.parse_args()
    if args.run_now:
        result = run_pipeline()
        print(result)
        sys.exit(0 if "error" not in result else 1)
