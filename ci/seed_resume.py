"""
GitHub Actions step: reads RESUME_PROFILE_JSON secret and inserts it into
jobs.db so the pipeline can search jobs without needing the original PDF.

Run once per workflow run before daily_runner.py.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import init_db, get_latest_resume_profile, save_resume_profile, set_primary_resume

def main():
    raw = os.environ.get("RESUME_PROFILE_JSON", "").strip()
    if not raw:
        print("ERROR: RESUME_PROFILE_JSON secret is empty.")
        sys.exit(1)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: Could not parse RESUME_PROFILE_JSON: {e}")
        sys.exit(1)

    init_db()

    # If profile already exists with same filename, skip to avoid duplicates
    existing = get_latest_resume_profile()
    if existing and existing.get("filename") == data.get("filename", "resume.pdf"):
        print(f"Resume profile already in DB: {existing['filename']} — skipping seed.")
        return

    filename = data.get("filename", "resume.pdf")
    raw_text = data.get("raw_text", "")
    parsed   = data.get("parsed_profile", data)  # support both wrapper and bare profile

    resume_id = save_resume_profile(filename, raw_text, parsed)
    set_primary_resume(resume_id)
    print(f"Seeded resume profile: {filename} (id={resume_id})")


if __name__ == "__main__":
    main()
