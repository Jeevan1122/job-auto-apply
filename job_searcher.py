from __future__ import annotations

"""
Job search from: LinkedIn, Indeed, Greenhouse, Glassdoor, Dice, Monster
All free — no API keys required (except optional Adzuna/JSearch for extra volume).
Filters: US only, fulltime + contract + remote, posted in last 24 hours.
"""
import asyncio
import hashlib
import json
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

from openai import OpenAI
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import (
    ADZUNA_APP_ID, ADZUNA_APP_KEY,
    JSEARCH_API_KEY,
    GEMINI_API_KEY, GEMINI_BASE_URL, RELEVANCE_SCORE_MODEL,
    MAX_JOBS_PER_RUN, JOB_TYPES
)
from database import upsert_job, update_job_score, get_jobs_for_scoring

logger = logging.getLogger(__name__)
_client: OpenAI | None = None

def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=GEMINI_API_KEY, base_url=GEMINI_BASE_URL)
    return _client

TIMEOUT = httpx.Timeout(30.0)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _job_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:16]


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def _normalize_type(raw: str) -> str:
    raw = raw.lower()
    if "contract" in raw:
        return "contract"
    if "remote" in raw:
        return "remote"
    return "fulltime"


# ── 1. LinkedIn ────────────────────────────────────────────────────────────────
# Uses LinkedIn's public guest jobs API — no login required

async def _search_linkedin(client: httpx.AsyncClient, keywords: list[str]) -> list[dict]:
    jobs: list[dict] = []
    # f_JT: F=fulltime, C=contract, f_TPR: r86400 = last 24 hours
    for keyword in keywords[:4]:
        for jtype_code, jtype_label in [("F", "fulltime"), ("C", "contract")]:
            try:
                params = {
                    "keywords": keyword,
                    "location": "United States",
                    "f_JT": jtype_code,
                    "f_TPR": "r86400",
                    "f_WT": "2",        # remote
                    "start": "0",
                    "count": "25",
                }
                r = await client.get(
                    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
                    params=params,
                    headers=HEADERS,
                    timeout=TIMEOUT,
                )
                if r.status_code != 200:
                    continue
                html = r.text
                job_ids   = re.findall(r'data-entity-urn="urn:li:jobPosting:(\d+)"', html)
                titles    = re.findall(r'class="base-search-card__title"[^>]*>\s*(.*?)\s*</h3>', html, re.DOTALL)
                companies = re.findall(r'class="base-search-card__subtitle"[^>]*>.*?<a[^>]*>\s*(.*?)\s*</a>', html, re.DOTALL)
                locations = re.findall(r'class="job-search-card__location"[^>]*>\s*(.*?)\s*</span>', html, re.DOTALL)

                for i, jid in enumerate(job_ids):
                    url = f"https://www.linkedin.com/jobs/view/{jid}/"
                    jobs.append({
                        "job_id":      _job_id(url),
                        "title":       _strip_html(titles[i])    if i < len(titles)    else "Unknown",
                        "company":     _strip_html(companies[i]) if i < len(companies) else "Unknown",
                        "location":    _strip_html(locations[i]) if i < len(locations) else "US",
                        "url":         url,
                        "source":      "LinkedIn",
                        "description": "",
                        "job_type":    jtype_label,
                    })
                await asyncio.sleep(1)
            except Exception as e:
                logger.warning("LinkedIn '%s' error: %s", keyword, e)
    return jobs


# ── 2. Indeed ─────────────────────────────────────────────────────────────────
# Uses Indeed's public RSS feed — no key required

async def _search_indeed(client: httpx.AsyncClient, keywords: list[str]) -> list[dict]:
    jobs: list[dict] = []
    for keyword in keywords[:4]:
        for jtype, jtype_label in [("fulltime", "fulltime"), ("contract", "contract")]:
            try:
                params = {
                    "q":       keyword,
                    "l":       "United States",
                    "jt":      jtype,
                    "fromage": "1",       # last 24 hours
                    "sort":    "date",
                }
                r = await client.get(
                    "https://www.indeed.com/rss",
                    params=params,
                    headers=HEADERS,
                    timeout=TIMEOUT,
                )
                if r.status_code != 200:
                    continue
                root = ET.fromstring(r.text)
                ns = {"dc": "http://purl.org/dc/elements/1.1/"}
                for item in root.findall(".//item"):
                    title_el   = item.find("title")
                    link_el    = item.find("link")
                    desc_el    = item.find("description")
                    company_el = item.find("dc:creator", ns)

                    raw_title = title_el.text  if title_el   is not None else ""
                    url       = link_el.text   if link_el    is not None else ""
                    desc      = _strip_html(desc_el.text if desc_el is not None else "")
                    company   = company_el.text if company_el is not None else "Unknown"

                    if not url:
                        continue

                    # "Job Title - Company Name" format
                    title = raw_title
                    if " - " in raw_title:
                        parts   = raw_title.rsplit(" - ", 1)
                        title   = parts[0].strip()
                        company = parts[1].strip() if company == "Unknown" else company

                    jobs.append({
                        "job_id":      _job_id(url),
                        "title":       title,
                        "company":     company,
                        "location":    "US",
                        "url":         url,
                        "source":      "Indeed",
                        "description": desc[:2000],
                        "job_type":    jtype_label,
                    })
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning("Indeed '%s' error: %s", keyword, e)
    return jobs


# ── 3. Greenhouse ─────────────────────────────────────────────────────────────
# Uses Greenhouse's public job board API — completely free, no key needed

GREENHOUSE_COMPANIES = [
    # Big Tech & FAANG-adjacent
    "airbnb", "stripe", "coinbase", "robinhood", "brex", "plaid",
    "databricks", "confluent", "hashicorp", "cloudflare", "figma",
    "notion", "airtable", "retool", "linear", "vercel", "netlify",
    # Finance & Fintech
    "chime", "affirm", "carta", "rippling", "gusto", "mercury",
    # Healthcare & Biotech
    "oscar", "ro", "hims",
    # E-commerce & Marketplace
    "faire", "whatnot", "StockX",
    # Infrastructure & DevTools
    "pulumi", "temporal", "dbt-labs", "prefect",
    # Other top employers
    "duolingo", "discord", "canva", "benchling", "scale-ai",
    "nerdio", "gem", "lattice", "leapsome",
]

async def _search_greenhouse(client: httpx.AsyncClient, keywords: list[str]) -> list[dict]:
    jobs: list[dict] = []
    kw_lower = [k.lower() for k in keywords]

    async def _fetch_company(company: str):
        try:
            r = await client.get(
                f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs",
                params={"content": "true"},
                timeout=TIMEOUT,
            )
            if r.status_code != 200:
                return
            for item in r.json().get("jobs", []):
                title = item.get("title", "")
                if not any(kw in title.lower() for kw in kw_lower):
                    continue
                url = item.get("absolute_url", "")
                if not url:
                    continue
                location = item.get("location", {}).get("name", "US")
                is_remote = "remote" in location.lower()
                jobs.append({
                    "job_id":      _job_id(url),
                    "title":       title,
                    "company":     company.replace("-", " ").title(),
                    "location":    location,
                    "url":         url,
                    "source":      "Greenhouse",
                    "description": _strip_html(item.get("content", ""))[:2000],
                    "job_type":    "remote" if is_remote else "fulltime",
                })
        except Exception as e:
            logger.debug("Greenhouse %s: %s", company, e)

    await asyncio.gather(*[_fetch_company(c) for c in GREENHOUSE_COMPANIES])
    return jobs


# ── 4. Glassdoor ──────────────────────────────────────────────────────────────
# Scrapes Glassdoor's job search page JSON payload

async def _search_glassdoor(client: httpx.AsyncClient, keywords: list[str]) -> list[dict]:
    jobs: list[dict] = []
    for keyword in keywords[:3]:
        try:
            params = {
                "sc.keyword": keyword,
                "locT":       "N",
                "locId":      "1",
                "jobType":    "",
                "fromAge":    "1",
                "sort":       "date",
            }
            r = await client.get(
                "https://www.glassdoor.com/Job/jobs.htm",
                params=params,
                headers={
                    **HEADERS,
                    "Referer": "https://www.glassdoor.com/",
                    "Accept":  "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
                timeout=TIMEOUT,
            )
            if r.status_code != 200:
                continue

            # Extract JSON from the Apollo cache embedded in the page
            match = re.search(
                r'"JobListingSearchResult".*?"jobListings"\s*:\s*(\[.*?\])',
                r.text, re.DOTALL
            )
            if not match:
                # Fallback: extract job cards from HTML
                job_ids  = re.findall(r'data-id="(\d+)"', r.text)
                titles   = re.findall(r'class="job-title[^"]*"[^>]*>(.*?)</(?:span|a|div)>', r.text, re.DOTALL)
                employers = re.findall(r'class="employer-name[^"]*"[^>]*>(.*?)</(?:span|a|div)>', r.text, re.DOTALL)
                for i, jid in enumerate(job_ids[:20]):
                    url = f"https://www.glassdoor.com/job-listing/j?jl={jid}"
                    jobs.append({
                        "job_id":      _job_id(url),
                        "title":       _strip_html(titles[i])    if i < len(titles)    else "Unknown",
                        "company":     _strip_html(employers[i]) if i < len(employers) else "Unknown",
                        "location":    "US",
                        "url":         url,
                        "source":      "Glassdoor",
                        "description": "",
                        "job_type":    "fulltime",
                    })
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning("Glassdoor '%s' error: %s", keyword, e)
    return jobs


# ── 5. Dice ───────────────────────────────────────────────────────────────────
# Uses Dice's public search API — no key required

async def _search_dice(client: httpx.AsyncClient, keywords: list[str]) -> list[dict]:
    jobs: list[dict] = []
    for keyword in keywords[:4]:
        try:
            params = {
                "q":                              keyword,
                "countryCode":                    "US",
                "radius":                         "30",
                "radiusUnit":                     "mi",
                "page":                           "1",
                "pageSize":                       "30",
                "filters.postedDate":             "ONE_DAY",
                "filters.employmentType":         "FULLTIME|CONTRACTS",
                "filters.workFromHomeAvailability": "Remote|Hybrid",
                "language":                       "en",
            }
            r = await client.get(
                "https://job-search-api.scoups.com/v1/jobs/search",
                params=params,
                headers=HEADERS,
                timeout=TIMEOUT,
            )
            dice_items: list = []
            if r.status_code == 200:
                try:
                    dice_items = r.json().get("data", [])
                except Exception:
                    pass  # empty body → fall through to RSS
            if dice_items:
                for item in dice_items:
                    url = (
                        item.get("applyDataRequired", {}).get("applyUrl")
                        or f"https://www.dice.com/jobs/detail/{item.get('id','')}"
                    )
                    emp_types = item.get("employmentType", [])
                    jtype = "contract" if any("contract" in str(e).lower() for e in emp_types) else "fulltime"
                    wfh = item.get("workFromHomeAvailability", "").lower()
                    if "remote" in wfh:
                        jtype = "remote"
                    company = item.get("companyName") or "Unknown"
                    if isinstance(item.get("companyPageUrl"), dict):
                        company = item["companyPageUrl"].get("displayName", company)
                    jobs.append({
                        "job_id":      _job_id(url),
                        "title":       item.get("title", ""),
                        "company":     company,
                        "location":    "Remote" if "remote" in wfh else item.get("location", "US"),
                        "url":         url,
                        "source":      "Dice",
                        "description": _strip_html(item.get("jobDescription", ""))[:2000],
                        "job_type":    jtype,
                    })
            else:
                # Fallback: Dice RSS
                r2 = await client.get(
                    f"https://www.dice.com/jobs/search/rss?q={keyword.replace(' ','+')}",
                    headers=HEADERS, timeout=TIMEOUT,
                )
                if r2.status_code == 200:
                    root = ET.fromstring(r2.text)
                    for item in root.findall(".//item"):
                        title_el = item.find("title")
                        link_el  = item.find("link")
                        desc_el  = item.find("description")
                        url = link_el.text if link_el is not None else ""
                        if url:
                            jobs.append({
                                "job_id":      _job_id(url),
                                "title":       title_el.text if title_el is not None else "",
                                "company":     "Unknown",
                                "location":    "US",
                                "url":         url,
                                "source":      "Dice",
                                "description": _strip_html(desc_el.text if desc_el is not None else "")[:2000],
                                "job_type":    "fulltime",
                            })
        except Exception as e:
            logger.warning("Dice '%s' error: %s", keyword, e)
    return jobs


# ── 6. Monster ────────────────────────────────────────────────────────────────
# Uses Monster's public job search — no key required

async def _search_monster(client: httpx.AsyncClient, keywords: list[str]) -> list[dict]:
    jobs: list[dict] = []
    for keyword in keywords[:3]:
        try:
            params = {
                "q":        keyword,
                "where":    "United States",
                "sort":     "d",          # date descending
                "jobType":  "fulltime",
                "age":      "1",          # last 24 hours
                "intcid":   "skr_navigation_nhpso_searchMain",
            }
            r = await client.get(
                "https://www.monster.com/jobs/search",
                params=params,
                headers={
                    **HEADERS,
                    "Accept": "text/html,application/xhtml+xml",
                },
                timeout=TIMEOUT,
            )
            if r.status_code != 200:
                continue

            # Extract JSON-LD structured data from the page
            ld_blocks = re.findall(
                r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
                r.text, re.DOTALL
            )
            for block in ld_blocks:
                try:
                    data = json.loads(block)
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        if item.get("@type") != "JobPosting":
                            continue
                        url = item.get("url", "")
                        if not url:
                            continue
                        org   = item.get("hiringOrganization", {})
                        loc   = item.get("jobLocation", {})
                        addr  = loc.get("address", {}) if isinstance(loc, dict) else {}
                        location_str = addr.get("addressLocality", "US") if isinstance(addr, dict) else "US"
                        emp_type = str(item.get("employmentType", "FULL_TIME"))
                        jobs.append({
                            "job_id":      _job_id(url),
                            "title":       item.get("title", ""),
                            "company":     org.get("name", "Unknown") if isinstance(org, dict) else "Unknown",
                            "location":    location_str,
                            "url":         url,
                            "source":      "Monster",
                            "description": _strip_html(item.get("description", ""))[:2000],
                            "job_type":    _normalize_type(emp_type),
                        })
                except Exception:
                    pass
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning("Monster '%s' error: %s", keyword, e)
    return jobs


# ── Dedup & filter ─────────────────────────────────────────────────────────────

def _deduplicate(jobs: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for job in jobs:
        url = job.get("url", "")
        if url and url not in seen:
            seen.add(url)
            out.append(job)
    return out


def _filter_by_job_type(jobs: list[dict]) -> list[dict]:
    if not JOB_TYPES:
        return jobs
    return [j for j in jobs if j.get("job_type", "fulltime") in JOB_TYPES]


# ── Relevance scoring ──────────────────────────────────────────────────────────

_SCORE_PROMPT = """Rate the relevance of these job listings to the candidate profile below.
Return a JSON object with a "results" array containing one object per job, in the same order:
{{"results": [{{"job_id": "...", "score": 0.85, "reason": "Brief reason"}}]}}

Scores: 0.0 = completely irrelevant, 1.0 = perfect match.

Candidate profile:
{profile_summary}

Jobs:
{jobs_text}"""


def _profile_summary(profile: dict) -> str:
    return json.dumps({
        "titles":    profile.get("job_titles", []),
        "skills":    profile.get("skills", {}),
        "years_exp": profile.get("years_of_experience", 0),
        "industries": profile.get("industries", []),
        "keywords":  profile.get("keywords", []),
    }, indent=2)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def _score_batch(jobs_batch: list[dict], profile: dict) -> list[dict]:
    jobs_text = "\n\n".join(
        f"job_id: {j['job_id']}\nTitle: {j['title']}\nCompany: {j['company']}\n"
        f"Location: {j['location']}\nDescription: {j.get('description','')[:600]}"
        for j in jobs_batch
    )
    prompt = _SCORE_PROMPT.format(
        profile_summary=_profile_summary(profile),
        jobs_text=jobs_text,
    )
    response = _get_client().chat.completions.create(
        model=RELEVANCE_SCORE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    data = json.loads(response.choices[0].message.content)
    return data.get("results", data) if isinstance(data, dict) else data


def score_jobs(profile: dict, today: str) -> int:
    jobs = get_jobs_for_scoring(today)
    if not jobs:
        return 0
    scored = 0
    for i in range(0, len(jobs), 5):
        batch = jobs[i: i + 5]
        try:
            results = _score_batch(batch, profile)
            for r in results:
                update_job_score(r["job_id"], r["score"], r.get("reason", ""))
                scored += 1
        except Exception as e:
            logger.error("Scoring batch %d failed: %s", i // 5, e)
            for j in batch:
                update_job_score(j["job_id"], 0.0, "scoring_error")
    return scored


# ── Main entry ─────────────────────────────────────────────────────────────────

async def _gather_jobs(keywords: list[str]) -> list[dict]:
    async with httpx.AsyncClient(follow_redirects=True, headers=HEADERS) as client:
        results = await asyncio.gather(
            _search_linkedin(client, keywords),
            _search_indeed(client, keywords),
            _search_greenhouse(client, keywords),
            _search_glassdoor(client, keywords),
            _search_dice(client, keywords),
            _search_monster(client, keywords),
            return_exceptions=True,
        )

    all_jobs: list[dict] = []
    counts: dict[str, int] = {}
    for r in results:
        if isinstance(r, list):
            for j in r:
                src = j.get("source", "?")
                counts[src] = counts.get(src, 0) + 1
            all_jobs.extend(r)
        else:
            logger.warning("Source error: %s", r)

    logger.info("Jobs found by source: %s", counts)
    return all_jobs


def search_and_store_jobs(profile: dict, max_jobs: int = MAX_JOBS_PER_RUN) -> int:
    keywords = (
        profile.get("job_titles", [])[:3]
        + profile.get("keywords", [])[:2]
    ) or ["software engineer"]

    all_jobs = asyncio.run(_gather_jobs(keywords))
    all_jobs = _deduplicate(all_jobs)
    all_jobs = _filter_by_job_type(all_jobs)
    all_jobs = all_jobs[:max_jobs]

    new_count = 0
    for job in all_jobs:
        if upsert_job(job):
            new_count += 1

    logger.info("Stored %d new jobs (from %d found)", new_count, len(all_jobs))
    return new_count
