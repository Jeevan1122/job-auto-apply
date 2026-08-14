from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

from config import GOOGLE_SHEET_ID, CREDENTIALS_PATH
from database import get_all_jobs, get_all_daily_summaries

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_APPS_HEADERS = [
    "Date", "Company", "Job Title", "Location", "Source",
    "Job Type", "Relevance Score", "Status", "URL", "Applied At", "Notes"
]
_SUMMARY_HEADERS = [
    "Date", "Jobs Found", "Applied", "Failed",
    "Manual Review", "Skipped", "Top Companies"
]


def _get_client():
    creds_path = Path(CREDENTIALS_PATH)
    if not creds_path.exists():
        raise FileNotFoundError(
            f"Google credentials file not found at {CREDENTIALS_PATH}. "
            "See setup instructions in OVERVIEW.md."
        )
    creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    return gspread.authorize(creds)


def _get_or_create_sheet(spreadsheet, title: str, headers: list[str]):
    try:
        ws = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=len(headers))
        ws.append_row(headers)
    # Ensure header row exists
    first_row = ws.row_values(1)
    if not first_row:
        ws.append_row(headers)
    return ws


def sync_to_sheets() -> bool:
    """Push all data to Google Sheets. Returns True on success."""
    if not GOOGLE_SHEET_ID:
        logger.warning("GOOGLE_SHEET_ID not configured — skipping Sheets sync")
        return False

    try:
        gc = _get_client()
        spreadsheet = gc.open_by_key(GOOGLE_SHEET_ID)

        # ── Applications sheet ────────────────────────────────────────────────
        ws_apps = _get_or_create_sheet(spreadsheet, "Applications", _APPS_HEADERS)
        jobs = get_all_jobs(limit=1000)
        rows = []
        for j in jobs:
            rows.append([
                j.get("date", ""),
                j.get("company", ""),
                j.get("title", ""),
                j.get("location", ""),
                j.get("source", ""),
                j.get("job_type", ""),
                round(j.get("relevance_score", 0.0), 2),
                j.get("status", ""),
                j.get("url", ""),
                j.get("applied_at", "") or "",
                j.get("notes", "") or "",
            ])
        ws_apps.clear()
        ws_apps.append_row(_APPS_HEADERS)
        if rows:
            ws_apps.append_rows(rows)

        # ── Daily Summary sheet ───────────────────────────────────────────────
        ws_sum = _get_or_create_sheet(spreadsheet, "Daily Summary", _SUMMARY_HEADERS)
        summaries = get_all_daily_summaries()
        sum_rows = []
        for s in summaries:
            companies = s.get("top_companies", [])
            sum_rows.append([
                s.get("date", ""),
                s.get("jobs_found", 0),
                s.get("jobs_applied", 0),
                s.get("jobs_failed", 0),
                s.get("jobs_manual", 0),
                s.get("jobs_skipped", 0),
                ", ".join(companies) if isinstance(companies, list) else str(companies),
            ])
        ws_sum.clear()
        ws_sum.append_row(_SUMMARY_HEADERS)
        if sum_rows:
            ws_sum.append_rows(sum_rows)

        logger.info("Google Sheets sync complete")
        return True
    except Exception as e:
        logger.error("Google Sheets sync failed: %s", e)
        return False
