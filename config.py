import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

# ── Core ──────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

# ── Job Board APIs ─────────────────────────────────────────────────────────────
ADZUNA_APP_ID  = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "")
JSEARCH_API_KEY = os.getenv("JSEARCH_API_KEY", "")

# ── LinkedIn ──────────────────────────────────────────────────────────────────
LINKEDIN_EMAIL    = os.getenv("LINKEDIN_EMAIL", "")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD", "")

# ── Candidate info (used in application forms) ────────────────────────────────
CANDIDATE_NAME       = os.getenv("CANDIDATE_NAME", "")
CANDIDATE_PHONE      = os.getenv("CANDIDATE_PHONE", "")
CANDIDATE_LINKEDIN   = os.getenv("CANDIDATE_LINKEDIN", "")
CANDIDATE_WEBSITE    = os.getenv("CANDIDATE_WEBSITE", "")

# ── Screening-question defaults ───────────────────────────────────────────────
WORK_AUTHORIZED      = os.getenv("WORK_AUTHORIZED", "yes")   # yes / no
REQUIRES_SPONSORSHIP = os.getenv("REQUIRES_SPONSORSHIP", "no")  # yes / no
SALARY_MIN           = os.getenv("SALARY_MIN", "100000")
SALARY_MAX           = os.getenv("SALARY_MAX", "150000")
NOTICE_PERIOD        = os.getenv("NOTICE_PERIOD", "2 weeks")
WILLING_TO_RELOCATE  = os.getenv("WILLING_TO_RELOCATE", "no")

# ── Tuning ────────────────────────────────────────────────────────────────────
COUNTRY            = os.getenv("COUNTRY", "us")
MAX_JOBS_PER_RUN   = int(os.getenv("MAX_JOBS_PER_RUN", "50"))
MIN_RELEVANCE_SCORE = float(os.getenv("MIN_RELEVANCE_SCORE", "0.65"))
DAILY_RUN_HOUR     = int(os.getenv("DAILY_RUN_HOUR", "9"))
DAILY_RUN_MINUTE   = int(os.getenv("DAILY_RUN_MINUTE", "0"))
HEADLESS           = os.getenv("HEADLESS", "true").lower() == "true"

_raw_job_types = os.getenv("JOB_TYPES", "fulltime,contract,remote")
JOB_TYPES = [t.strip().lower() for t in _raw_job_types.split(",") if t.strip()]

# ── OpenAI models ─────────────────────────────────────────────────────────────
RESUME_PARSE_MODEL   = "gpt-4.1-mini"
RELEVANCE_SCORE_MODEL = "gpt-4.1-mini"
COVER_LETTER_MODEL   = "gpt-4.1-mini"
TAILOR_MODEL         = "gpt-4.1-mini"

# ── Paths ─────────────────────────────────────────────────────────────────────
UPLOADS_DIR      = os.path.join(os.path.dirname(__file__), "uploads")
DB_PATH          = os.path.join(os.path.dirname(__file__), "jobs.db")
CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), "credentials.json")
# In GitHub Actions set REPORTS_DIR=reports; locally falls back to Desktop
EXCEL_OUTPUT_DIR = os.getenv("REPORTS_DIR", str(Path.home() / "Desktop"))

os.makedirs(UPLOADS_DIR, exist_ok=True)
