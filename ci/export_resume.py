"""
Run this ONCE on your Mac to generate the value for the RESUME_PROFILE_JSON secret.

  python ci/export_resume.py

Copy the printed JSON and paste it into:
  GitHub repo → Settings → Secrets and variables → Actions → New secret
  Name:  RESUME_PROFILE_JSON
  Value: <paste the JSON here>
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import init_db, get_latest_resume_profile

def main():
    init_db()
    profile = get_latest_resume_profile()
    if not profile:
        print("No resume profile found in jobs.db.")
        print("Upload your resume via the Streamlit UI first, then run this script.")
        sys.exit(1)

    export = {
        "filename":       profile["filename"],
        "raw_text":       profile.get("raw_text", ""),
        "parsed_profile": profile["parsed_profile"],
    }

    output = json.dumps(export, indent=2)
    print("\n" + "="*60)
    print("Copy everything between the lines and paste as the")
    print("RESUME_PROFILE_JSON GitHub Secret value:")
    print("="*60)
    print(output)
    print("="*60 + "\n")

    # Also save to a local file for convenience
    out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ci", "resume_profile_export.json")
    with open(out_path, "w") as f:
        json.dump(export, f, indent=2)
    print(f"Also saved to: {out_path}")
    print("(Do NOT commit this file — it contains your personal resume data.)")


if __name__ == "__main__":
    main()
