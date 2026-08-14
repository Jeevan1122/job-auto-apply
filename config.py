import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

# ── Supabase ──────────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# ── AI (Gemini — free tier) ───────────────────────────────────────────────────
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# ── AI models ─────────────────────────────────────────────────────────────────
RESUME_PARSE_MODEL    = "gemini-2.0-flash"
RELEVANCE_SCORE_MODEL = "gemini-2.0-flash"
COVER_LETTER_MODEL    = "gemini-2.0-flash"
TAILOR_MODEL          = "gemini-2.0-flash"

# ── Optional job board APIs (leave blank if unused) ──────────────────────────
ADZUNA_APP_ID   = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY  = os.getenv("ADZUNA_APP_KEY", "")
JSEARCH_API_KEY = os.getenv("JSEARCH_API_KEY", "")

# ── Tuning (overridable via env) ──────────────────────────────────────────────
COUNTRY             = os.getenv("COUNTRY", "us")
MAX_JOBS_PER_RUN    = int(os.getenv("MAX_JOBS_PER_RUN", "50"))
MIN_RELEVANCE_SCORE = float(os.getenv("MIN_RELEVANCE_SCORE", "0.65"))

_raw_job_types = os.getenv("JOB_TYPES", "fulltime,contract,remote")
JOB_TYPES = [t.strip().lower() for t in _raw_job_types.split(",") if t.strip()]

# ── Profile defaults (empty — users enter these in the UI) ───────────────────
LINKEDIN_EMAIL       = os.getenv("LINKEDIN_EMAIL", "")
LINKEDIN_PASSWORD    = os.getenv("LINKEDIN_PASSWORD", "")
CANDIDATE_NAME       = os.getenv("CANDIDATE_NAME", "")
CANDIDATE_PHONE      = os.getenv("CANDIDATE_PHONE", "")
CANDIDATE_LINKEDIN   = os.getenv("CANDIDATE_LINKEDIN", "")
CANDIDATE_WEBSITE    = os.getenv("CANDIDATE_WEBSITE", "")
WORK_AUTHORIZED      = os.getenv("WORK_AUTHORIZED", "yes")
REQUIRES_SPONSORSHIP = os.getenv("REQUIRES_SPONSORSHIP", "no")
SALARY_MIN           = os.getenv("SALARY_MIN", "")
SALARY_MAX           = os.getenv("SALARY_MAX", "")
NOTICE_PERIOD        = os.getenv("NOTICE_PERIOD", "")
WILLING_TO_RELOCATE  = os.getenv("WILLING_TO_RELOCATE", "no")
HEADLESS             = os.getenv("HEADLESS", "true").lower() == "true"
DAILY_RUN_HOUR       = int(os.getenv("DAILY_RUN_HOUR", "6"))
DAILY_RUN_MINUTE     = int(os.getenv("DAILY_RUN_MINUTE", "0"))
COVER_LETTER_MODEL   = TAILOR_MODEL

# ── Paths ─────────────────────────────────────────────────────────────────────
UPLOADS_DIR      = os.path.join(os.path.dirname(__file__), "uploads")
DB_PATH          = os.path.join(os.path.dirname(__file__), "jobs.db")
EXCEL_OUTPUT_DIR = os.getenv("REPORTS_DIR", str(Path.home() / "Desktop"))

os.makedirs(UPLOADS_DIR, exist_ok=True)
