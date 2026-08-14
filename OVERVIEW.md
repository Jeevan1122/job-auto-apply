# Automated Job Application System — Overview

## What It Does

You upload your resume once. Every day, the system:
1. Searches multiple job boards for roles relevant to your profile
2. Scores each job for relevance using AI
3. Automatically applies to matching positions
4. Tracks every application in a local database
5. Updates your Google Sheet at end of day with a full summary

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Streamlit Web UI                        │
│  (Upload Resume · View Dashboard · Track Applications)      │
└──────────────────────────┬──────────────────────────────────┘
                           │
          ┌────────────────▼────────────────┐
          │         Daily Runner             │
          │  (Triggered by APScheduler       │
          │   every day at configured time)  │
          └──┬──────────┬──────────┬────────┘
             │          │          │
    ┌────────▼──┐  ┌────▼────┐  ┌─▼──────────────┐
    │  Resume   │  │  Job    │  │  Job Applier    │
    │  Parser   │  │Searcher │  │  (Playwright)   │
    │ (Claude)  │  │(APIs)   │  │                 │
    └────────┬──┘  └────┬────┘  └─┬──────────────┘
             │          │          │
          ┌──▼──────────▼──────────▼──┐
          │       SQLite Database      │
          │  (jobs · daily_summary)    │
          └──────────────┬────────────┘
                         │
               ┌─────────▼──────────┐
               │   Google Sheets    │
               │ (Daily Sync via    │
               │    gspread)        │
               └────────────────────┘
```

---

## Components

### 1. Resume Parser (`resume_parser.py`)
- Accepts PDF or DOCX resume
- Extracts raw text using `pdfminer.six` / `python-docx`
- Sends text to **Claude claude-sonnet-4-6** which extracts:
  - Job titles you qualify for
  - Key skills (technical + soft)
  - Years of experience
  - Industry/domain
  - Location preference
  - Education
- Output is a structured profile stored in the database and used for all job searches

### 2. Job Searcher (`job_searcher.py`)
Queries multiple job board APIs in parallel:

| Source | Method | Free Tier |
|--------|--------|-----------|
| **Adzuna** | REST API | 250 calls/month |
| **JSearch (RapidAPI)** | REST API | 500 calls/month |
| **Remotive** | REST API | Unlimited (remote jobs) |
| **LinkedIn** | Playwright scraping | N/A |

- Deduplicates jobs across sources by URL
- Stores all found jobs with status `found`

### 3. Job Relevance Scorer (`job_searcher.py`)
- Sends each job description + your resume profile to **Claude**
- Claude returns a relevance score (0.0 – 1.0) with reasoning
- Only jobs above `MIN_RELEVANCE_SCORE` (default: 0.65) are queued for application
- Runs in batches to respect API rate limits

### 4. Job Applier (`job_applier.py`)
Uses **Playwright** (headless browser automation) to apply:

**LinkedIn Easy Apply**
- Logs into LinkedIn with your credentials
- Searches using your extracted job titles + skills
- Filters to "Easy Apply" only
- Clicks Easy Apply → fills form fields → uploads resume → submits
- Handles multi-step application forms

**Greenhouse / Lever / Workday (direct ATS)**
- Detects ATS type from job URL
- Fills standard fields: name, email, phone, resume upload, LinkedIn URL
- Submits and captures confirmation

**Fallback**
- Jobs that can't be auto-applied are marked `requires_manual` in the DB
- Shown highlighted in the dashboard for you to apply manually

### 5. Application Tracker (`database.py`)
SQLite database with two tables:

**`jobs` table**
```
id, job_id, title, company, location, url, source,
description, relevance_score, status, applied_at,
found_at, date, notes
```

Status values: `found` → `applying` → `applied` / `failed` / `skipped` / `requires_manual`

**`daily_summary` table**
```
id, date, jobs_found, jobs_applied, jobs_failed,
jobs_manual, top_companies, sheets_updated
```

**`resume_profile` table**
```
id, filename, raw_text, parsed_profile_json, created_at
```

### 6. Google Sheets Updater (`sheets_updater.py`)
Syncs to two sheets in your Google Spreadsheet at end of each day:

**Sheet: "Applications"**
| Date | Company | Job Title | Location | Source | Relevance | Status | URL | Applied At |
|------|---------|-----------|----------|--------|-----------|--------|-----|------------|

**Sheet: "Daily Summary"**
| Date | Jobs Found | Applied | Failed | Manual Review | Top Companies |
|------|-----------|---------|--------|---------------|---------------|

### 7. Scheduler (`scheduler.py`)
- Uses **APScheduler** with a `BlockingScheduler`
- Runs the full pipeline daily at your configured time (default: 9:00 AM)
- Can also be triggered manually via CLI or the Streamlit UI

### 8. Streamlit Web UI (`app.py`)
Four tabs:

- **Upload Resume** — drag & drop PDF/DOCX, triggers parsing, shows extracted profile
- **Dashboard** — today's stats: jobs found, applied, failed; relevance score distribution
- **Applications** — full searchable/filterable table of all applications with status
- **Settings** — configure run time, min relevance score, job search keywords, locations

---

## Tech Stack

| Layer | Library/Tool |
|-------|-------------|
| UI | Streamlit |
| AI / NLP | Anthropic Claude (claude-sonnet-4-6) |
| Browser Automation | Playwright (async) |
| Job APIs | Adzuna, JSearch (RapidAPI), Remotive |
| PDF Parsing | pdfminer.six |
| DOCX Parsing | python-docx |
| Database | SQLite via `sqlite3` |
| Google Sheets | gspread + google-auth |
| Scheduler | APScheduler |
| HTTP | httpx (async) |
| Env Config | python-dotenv |

---

## File Structure

```
job-auto-apply/
├── app.py                  # Streamlit UI entry point
├── config.py               # All configuration + env var loading
├── database.py             # SQLite schema + all DB operations
├── resume_parser.py        # PDF/DOCX → Claude → structured profile
├── job_searcher.py         # Job APIs + Claude relevance scoring
├── job_applier.py          # Playwright automation for applying
├── sheets_updater.py       # Google Sheets sync
├── daily_runner.py         # Orchestrates the full daily pipeline
├── scheduler.py            # APScheduler — runs daily_runner on schedule
├── requirements.txt
├── .env.example            # Template for all environment variables
├── credentials.json        # (you provide) Google Service Account key
└── uploads/                # Uploaded resumes stored here
```

---

## Environment Variables (`.env`)

```env
# Required
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_SHEET_ID=your_google_sheet_id_here

# Job Search APIs (get at least one)
ADZUNA_APP_ID=your_adzuna_app_id
ADZUNA_APP_KEY=your_adzuna_app_key
JSEARCH_API_KEY=your_rapidapi_key_for_jsearch

# LinkedIn auto-apply (optional but recommended)
LINKEDIN_EMAIL=you@email.com
LINKEDIN_PASSWORD=yourpassword

# Optional tuning
COUNTRY=us
MAX_JOBS_PER_RUN=50
MIN_RELEVANCE_SCORE=0.65
DAILY_RUN_HOUR=9
DAILY_RUN_MINUTE=0
HEADLESS=true
```

---

## Google Sheets Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → enable **Google Sheets API** + **Google Drive API**
3. Create a **Service Account** → download `credentials.json`
4. Share your Google Sheet with the service account email
5. Copy the Sheet ID from the URL into `.env`

The app auto-creates the "Applications" and "Daily Summary" worksheets on first run.

---

## API Setup

### Adzuna (Free — Recommended)
1. Sign up at [developer.adzuna.com](https://developer.adzuna.com)
2. Create an app → get `App ID` and `App Key`
3. 250 free API calls/month (each call returns up to 50 jobs)

### JSearch via RapidAPI (Optional)
1. Sign up at [rapidapi.com](https://rapidapi.com)
2. Subscribe to the **JSearch** API (free tier: 500 calls/month)
3. Copy the `X-RapidAPI-Key` into `.env` as `JSEARCH_API_KEY`

### Remotive (Free — Remote Jobs)
- No API key needed — completely free public API

---

## Daily Pipeline Flow

```
09:00 AM (or configured time)
    │
    ▼
Load active resume profile from DB
    │
    ▼
Search Adzuna + JSearch + Remotive in parallel
    │
    ▼
Deduplicate by URL → save all as status='found'
    │
    ▼
Score relevance with Claude (batch, 5 at a time)
    │
    ▼
Filter jobs with score >= MIN_RELEVANCE_SCORE
    │
    ▼
For each qualifying job:
  ├── Detect application type (LinkedIn / Greenhouse / Lever / Other)
  ├── Launch Playwright → auto-apply
  ├── On success → status='applied'
  └── On failure → status='failed' or 'requires_manual'
    │
    ▼
Build daily_summary record
    │
    ▼
Sync to Google Sheets (Applications + Daily Summary tabs)
    │
    ▼
Done — check dashboard for results
```

---

## Limitations & Honest Notes

| Limitation | Details |
|------------|---------|
| **LinkedIn ToS** | LinkedIn prohibits scraping/automation. Use at your own discretion. |
| **CAPTCHA** | If LinkedIn shows CAPTCHA, the applier will skip and mark as `requires_manual` |
| **Rate limits** | Adzuna free = 250 calls/month. ~8 runs/day max at 1 call/run |
| **ATS variation** | Workday, iCIMS, and custom portals are harder to automate — marked as manual |
| **Application quality** | Auto-applied cover letters use Claude to generate context-aware text |
| **Multi-page forms** | Handled for LinkedIn Easy Apply; complex multi-step forms may fail |

---

## How to Run

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Set up environment
cp .env.example .env
# Edit .env with your API keys

# 3. Place credentials.json in project root

# 4. Start the web UI
streamlit run app.py

# 5. In a separate terminal, start the daily scheduler
python scheduler.py

# OR run the pipeline immediately (one-time)
python daily_runner.py --run-now
```

---

## Google Sheet Output Example

### "Daily Summary" tab
| Date | Jobs Found | Applied | Failed | Manual Review |
|------|-----------|---------|--------|---------------|
| 2026-08-13 | 47 | 31 | 4 | 12 |
| 2026-08-14 | 52 | 38 | 3 | 11 |

### "Applications" tab
| Date | Company | Job Title | Location | Source | Relevance | Status | URL |
|------|---------|-----------|----------|--------|-----------|--------|-----|
| 2026-08-13 | Stripe | Backend Engineer | Remote | LinkedIn | 0.91 | Applied | ... |
| 2026-08-13 | Airbnb | Python Developer | SF | Adzuna | 0.84 | Applied | ... |
| 2026-08-13 | Netflix | Sr. Engineer | LA | JSearch | 0.71 | Manual | ... |
