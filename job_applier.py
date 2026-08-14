from __future__ import annotations

"""
Auto-apply engine using Playwright.
Supports: LinkedIn Easy Apply, Greenhouse, Lever, Workday (basic), Generic fallback.

For each job it:
  1. Detects which ATS is being used
  2. Tailors cover letter + resume bullets via AI
  3. Extracts every visible form question using JavaScript
  4. Uses AI to answer each question based on the candidate profile
  5. Fills the form, uploads resume, submits
"""
import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Optional

from openai import OpenAI
from playwright.async_api import (
    async_playwright, Page, BrowserContext,
    TimeoutError as PWTimeout
)

from config import (
    LINKEDIN_EMAIL, LINKEDIN_PASSWORD,
    CANDIDATE_NAME, CANDIDATE_PHONE, CANDIDATE_LINKEDIN, CANDIDATE_WEBSITE,
    WORK_AUTHORIZED, REQUIRES_SPONSORSHIP,
    SALARY_MIN, SALARY_MAX, NOTICE_PERIOD, WILLING_TO_RELOCATE,
    HEADLESS, UPLOADS_DIR,
    OPENAI_API_KEY, COVER_LETTER_MODEL,
)
from resume_tailor import tailor_application

logger = logging.getLogger(__name__)
_ai = OpenAI(api_key=OPENAI_API_KEY)

_RESUME_PATH: Optional[str] = None


def set_resume_path(path: str):
    global _RESUME_PATH
    _RESUME_PATH = path


def _get_resume_file() -> Optional[str]:
    if _RESUME_PATH and Path(_RESUME_PATH).exists():
        return _RESUME_PATH
    upload_dir = Path(UPLOADS_DIR)
    for pattern in ("*.pdf", "*.docx"):
        files = sorted(upload_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        if files:
            return str(files[0])
    return None


# ── ATS detection ──────────────────────────────────────────────────────────────

def detect_ats(url: str) -> str:
    u = url.lower()
    if "linkedin.com" in u:                                   return "linkedin"
    if "greenhouse.io" in u or "boards.greenhouse.io" in u:  return "greenhouse"
    if "lever.co" in u or "jobs.lever.co" in u:              return "lever"
    if "myworkdayjobs.com" in u or "wd1.myworkdayjobs" in u: return "workday"
    if "icims.com" in u:                                     return "icims"
    if "jobvite.com" in u:                                   return "jobvite"
    if "smartrecruiters.com" in u:                           return "smartrecruiters"
    if "ashbyhq.com" in u:                                   return "ashby"
    return "generic"


# ── Basic helpers ──────────────────────────────────────────────────────────────

async def _fill(page: Page, selector: str, value: str, timeout: int = 2000):
    if not value:
        return
    try:
        el = page.locator(selector).first
        if await el.is_visible(timeout=timeout):
            cur = await el.input_value()
            if not cur:
                await el.fill(value)
    except Exception:
        pass


async def _upload_resume(page: Page, selector: str = "input[type='file']"):
    resume = _get_resume_file()
    if not resume:
        return
    try:
        el = page.locator(selector).first
        if await el.count() > 0:
            await el.set_input_files(resume)
            await asyncio.sleep(1)
    except Exception:
        pass


def _split_name(profile: dict) -> tuple[str, str]:
    full = CANDIDATE_NAME or profile.get("full_name", "Applicant User")
    parts = full.strip().split(None, 1)
    return (parts[0], parts[1] if len(parts) > 1 else "User")


# ── AI-powered form question extractor ────────────────────────────────────────

_EXTRACT_JS = """() => {
    const results = [];
    const seenRadioGroups = new Set();

    function getQuestion(el) {
        const container = el.closest(
            '.jobs-easy-apply-form-element, .fb-form-element, fieldset, ' +
            '.form-group, .application-form-field, .artdeco-form__group, ' +
            '.greenhouse-job-board__field, .lever-field'
        );
        if (container) {
            const lbl = container.querySelector(
                'legend, label.jobs-easy-apply-form-element__label, ' +
                '.fb-form-element-label, .application-form-field__label, ' +
                '.artdeco-text-input--label, h3, h4'
            );
            if (lbl && lbl !== el) return lbl.innerText.trim().replace(/\\s+/g, ' ');
        }
        if (el.id) {
            const lbl = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
            if (lbl) return lbl.innerText.trim().replace(/\\s+/g, ' ');
        }
        return el.getAttribute('aria-label') || el.placeholder || el.name || '';
    }

    document.querySelectorAll('input, select, textarea').forEach(el => {
        const skip = ['hidden','file','submit','button','reset','image','search'];
        if (skip.includes(el.type)) return;
        if (el.offsetParent === null) return;
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) return;

        const question = getQuestion(el);
        const name = el.name || el.id || '';
        const id   = el.id   || '';

        if (el.type === 'radio') {
            if (!name || seenRadioGroups.has(name)) return;
            seenRadioGroups.add(name);
            const radios = document.querySelectorAll('input[type="radio"][name="' + CSS.escape(name) + '"]');
            const options = Array.from(radios).map(r => {
                let optLabel = '';
                if (r.id) {
                    const lbl = document.querySelector('label[for="' + CSS.escape(r.id) + '"]');
                    optLabel = lbl ? lbl.innerText.trim() : '';
                }
                if (!optLabel) {
                    const pLbl = r.closest('label');
                    optLabel = pLbl ? pLbl.innerText.trim() : r.value;
                }
                return {value: r.value, label: optLabel || r.value, checked: r.checked};
            });
            results.push({
                type: 'radio', name, question, options,
                current_value: (options.find(o => o.checked) || {}).value || ''
            });
            return;
        }

        if (el.type === 'checkbox') {
            results.push({type: 'checkbox', name, id, question, current_value: el.checked});
            return;
        }

        if (el.tagName === 'SELECT') {
            results.push({
                type: 'select', name, id, question,
                options: Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()})),
                current_value: el.value
            });
            return;
        }

        const type = el.tagName === 'TEXTAREA' ? 'textarea' : (el.type || 'text');
        results.push({type, name, id, question, placeholder: el.placeholder || '', current_value: el.value || ''});
    });

    return results;
}"""


async def _extract_form_questions(page: Page) -> list[dict]:
    try:
        return await page.evaluate(_EXTRACT_JS)
    except Exception as e:
        logger.debug("JS extraction failed: %s", e)
        return []


# ── AI question answerer ───────────────────────────────────────────────────────

def _ai_answer_form_questions(questions: list[dict], profile: dict) -> dict:
    """Ask OpenAI to answer every form field based on the candidate profile."""
    if not questions:
        return {}

    name_parts = _split_name(profile)
    candidate = {
        "full_name":            CANDIDATE_NAME or profile.get("full_name", f"{name_parts[0]} {name_parts[1]}"),
        "first_name":           name_parts[0],
        "last_name":            name_parts[1],
        "email":                profile.get("email", ""),
        "phone":                CANDIDATE_PHONE,
        "linkedin_url":         CANDIDATE_LINKEDIN,
        "website":              CANDIDATE_WEBSITE,
        "current_title":        profile.get("current_title", ""),
        "years_of_experience":  profile.get("years_of_experience", 0),
        "skills":               profile.get("skills", {}),
        "education":            profile.get("education", []),
        "location":             "United States",
        "authorized_to_work_in_us":   WORK_AUTHORIZED,
        "requires_visa_sponsorship":  REQUIRES_SPONSORSHIP,
        "salary_expectation_min":     SALARY_MIN,
        "salary_expectation_max":     SALARY_MAX,
        "notice_period":              NOTICE_PERIOD,
        "willing_to_relocate":        WILLING_TO_RELOCATE,
        "open_to_remote":             "yes",
        "languages":                  ["English"],
    }

    prompt = f"""You are an AI assistant filling out a job application form on behalf of a candidate.
For each form field below, return the most appropriate answer.

Candidate profile:
{json.dumps(candidate, indent=2)}

Form fields to fill (JSON array):
{json.dumps(questions, indent=2)}

Rules:
- Return a flat JSON object keyed by each field's "name" (use "id" if name is empty)
- radio/select: return the exact "value" string from the options list
- text/number/tel/email/textarea: return the answer as a plain string
- checkbox: return true or false
- Skip fields that already have a non-empty current_value
- "authorized to work in the US" → use authorized_to_work_in_us ("yes"/"no")
- "require / need sponsorship" → use requires_visa_sponsorship ("yes"/"no")
- "years of experience with [tech]" → look up the skill in the skills dict; if not found, estimate 0
- salary questions → use salary_expectation_min and salary_expectation_max
- "willing to relocate" → use willing_to_relocate
- "notice period" / "when can you start" → use notice_period
- For dropdowns pick the closest matching option from the provided options list; never invent a value
- Be honest and consistent with the profile

Return only valid JSON, no extra text."""

    try:
        resp = _ai.chat.completions.create(
            model=COVER_LETTER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        logger.warning("AI form answering failed: %s", e)
        return {}


# ── Smart page filler ──────────────────────────────────────────────────────────

async def _smart_fill_page(page: Page, profile: dict, tailored: dict):
    """
    1. Fast-fill the standard fields we always know (name, email, phone, …)
    2. Upload resume
    3. Extract all remaining visible form questions via JS
    4. Ask AI for answers
    5. Fill each answer using the correct Playwright API
    """
    name_parts = _split_name(profile)
    email = profile.get("email", "")

    # ── 1. Known fields ────────────────────────────────────────────────────────
    await _fill(page,
        "input[id*='firstName'], input[name='firstName'], "
        "input[name='first_name'], input[id*='first_name'], "
        "input[placeholder*='First name' i]",
        name_parts[0])
    await _fill(page,
        "input[id*='lastName'], input[name='lastName'], "
        "input[name='last_name'], input[id*='last_name'], "
        "input[placeholder*='Last name' i]",
        name_parts[1])
    await _fill(page,
        "input[name='name'], input[id='name'], input[placeholder*='Full name' i]",
        f"{name_parts[0]} {name_parts[1]}")
    await _fill(page,
        "input[type='email'], input[name='email'], input[id*='email']",
        email)
    await _fill(page,
        "input[name*='phone'], input[id*='phone'], input[type='tel']",
        CANDIDATE_PHONE)
    await _fill(page,
        "input[name*='linkedin'], input[id*='linkedin']",
        CANDIDATE_LINKEDIN)
    await _fill(page,
        "input[name*='website'], input[name*='portfolio'], input[id*='website']",
        CANDIDATE_WEBSITE)

    # Cover letter (if a textarea labelled "cover")
    cover_ta = page.locator("textarea[name*='cover' i], textarea[id*='cover' i]").first
    try:
        if await cover_ta.is_visible(timeout=800):
            val = await cover_ta.input_value()
            if not val:
                await cover_ta.fill(tailored.get("cover_letter", ""))
    except Exception:
        pass

    # ── 2. Resume upload ───────────────────────────────────────────────────────
    await _upload_resume(page)

    # ── 3. Extract questions ───────────────────────────────────────────────────
    try:
        questions = await _extract_form_questions(page)
        unfilled = [
            q for q in questions
            if not q.get("current_value") and q.get("question")
        ]
        if not unfilled:
            return

        # ── 4. AI answers ──────────────────────────────────────────────────────
        answers = _ai_answer_form_questions(unfilled, profile)
        if not answers:
            return

        # ── 5. Fill each answer ────────────────────────────────────────────────
        for field in unfilled:
            key = field.get("name") or field.get("id") or ""
            answer = answers.get(key)

            # If key not found, try fuzzy match by question text
            if answer is None:
                q_lower = field.get("question", "").lower()
                for ak, av in answers.items():
                    if ak.lower() in q_lower or q_lower in ak.lower():
                        answer = av
                        break

            if answer is None:
                continue

            try:
                ftype = field["type"]

                if ftype == "radio":
                    name = field["name"]
                    radio_val = str(answer)
                    # Try direct value match
                    sel = f"input[type='radio'][name='{name}'][value='{radio_val}']"
                    el = page.locator(sel).first
                    if await el.count() > 0:
                        await el.check()
                    else:
                        # Fuzzy match against option labels
                        for opt in field.get("options", []):
                            if radio_val.lower() in opt.get("label", "").lower():
                                r = page.locator(
                                    f"input[type='radio'][name='{name}'][value='{opt['value']}']"
                                ).first
                                if await r.count() > 0:
                                    await r.check()
                                    break

                elif ftype == "select":
                    sel = f"#{field['id']}" if field.get("id") else f"select[name='{field['name']}']"
                    try:
                        await page.locator(sel).first.select_option(str(answer))
                    except Exception:
                        # Try by visible text
                        for opt in field.get("options", []):
                            if str(answer).lower() in opt.get("text", "").lower():
                                await page.locator(sel).first.select_option(value=opt["value"])
                                break

                elif ftype == "checkbox":
                    sel = f"#{field['id']}" if field.get("id") else f"input[type='checkbox'][name='{field['name']}']"
                    el = page.locator(sel).first
                    checked = await el.is_checked()
                    if answer and not checked:
                        await el.check()
                    elif not answer and checked:
                        await el.uncheck()

                elif ftype in ("text", "number", "tel", "email", "textarea", "url"):
                    sel = f"#{field['id']}" if field.get("id") else f"[name='{field['name']}']"
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=500):
                        current = await el.input_value()
                        if not current:
                            await el.fill(str(answer))

            except Exception as ex:
                logger.debug("Could not fill field '%s': %s", key, ex)

    except Exception as e:
        logger.warning("Smart form fill error: %s", e)


# ── LinkedIn Easy Apply ────────────────────────────────────────────────────────

async def _linkedin_login(context: BrowserContext) -> bool:
    if not LINKEDIN_EMAIL or not LINKEDIN_PASSWORD:
        return False
    page = await context.new_page()
    try:
        await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_selector(
            "#username, input[name='session_key']", timeout=15000
        )
        await page.locator("#username, input[name='session_key']").first.fill(LINKEDIN_EMAIL)
        await page.locator("#password, input[name='session_password']").first.fill(LINKEDIN_PASSWORD)
        await page.click("button[type='submit']")
        await page.wait_for_timeout(5000)
        if "feed" in page.url or "checkpoint" not in page.url:
            logger.info("LinkedIn login successful")
            await page.close()
            return True
        await page.close()
        return False
    except Exception as e:
        logger.warning("LinkedIn login failed: %s", e)
        await page.close()
        return False


async def _linkedin_easy_apply(
    context: BrowserContext, job: dict, tailored: dict, profile: dict
) -> tuple[bool, str]:
    page = await context.new_page()
    try:
        await page.goto(job["url"], wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        easy_btn = page.locator(
            "button.jobs-apply-button, "
            "button[aria-label*='Easy Apply'], "
            "button[aria-label*='easy apply']"
        ).first
        if not await easy_btn.is_visible(timeout=5000):
            return False, "no_easy_apply_button"
        await easy_btn.click()
        await page.wait_for_timeout(2000)

        # Multi-step form — up to 15 steps
        for _step in range(15):
            await _smart_fill_page(page, profile, tailored)
            await page.wait_for_timeout(800)

            submit = page.locator("button[aria-label='Submit application']")
            if await submit.is_visible(timeout=1500):
                await submit.click()
                await page.wait_for_timeout(3000)
                return True, "applied"

            review = page.locator("button[aria-label='Review your application']")
            if await review.is_visible(timeout=1000):
                await review.click()
                await page.wait_for_timeout(1000)
                continue

            nxt = page.locator(
                "button[aria-label='Continue to next step'], "
                "button[aria-label='Next']"
            )
            if await nxt.is_visible(timeout=1000):
                await nxt.click()
                await page.wait_for_timeout(1000)
            else:
                break

        return False, "could_not_submit"
    except PWTimeout:
        return False, "timeout"
    except Exception as e:
        return False, str(e)[:80]
    finally:
        await page.close()


# ── Greenhouse ─────────────────────────────────────────────────────────────────

async def _apply_greenhouse(
    context: BrowserContext, job: dict, tailored: dict, profile: dict
) -> tuple[bool, str]:
    page = await context.new_page()
    try:
        await page.goto(job["url"], wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        await _smart_fill_page(page, profile, tailored)
        await page.click("input#submit_app, button[type='submit']")
        await page.wait_for_timeout(3000)
        if any(s in page.url for s in ["confirmation", "thank", "success"]):
            return True, "applied"
        return True, "submitted"
    except Exception as e:
        return False, str(e)[:80]
    finally:
        await page.close()


# ── Lever ──────────────────────────────────────────────────────────────────────

async def _apply_lever(
    context: BrowserContext, job: dict, tailored: dict, profile: dict
) -> tuple[bool, str]:
    page = await context.new_page()
    try:
        await page.goto(job["url"], wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        await _smart_fill_page(page, profile, tailored)
        await page.click("button[type='submit'], input[type='submit']")
        await page.wait_for_timeout(3000)
        return True, "applied"
    except Exception as e:
        return False, str(e)[:80]
    finally:
        await page.close()


# ── Ashby ──────────────────────────────────────────────────────────────────────

async def _apply_ashby(
    context: BrowserContext, job: dict, tailored: dict, profile: dict
) -> tuple[bool, str]:
    page = await context.new_page()
    try:
        await page.goto(job["url"], wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        await _smart_fill_page(page, profile, tailored)
        await page.click("button[type='submit']")
        await page.wait_for_timeout(3000)
        return True, "applied"
    except Exception as e:
        return False, str(e)[:80]
    finally:
        await page.close()


# ── Generic fallback ───────────────────────────────────────────────────────────

async def _apply_generic(
    context: BrowserContext, job: dict, tailored: dict, profile: dict
) -> tuple[bool, str]:
    page = await context.new_page()
    try:
        await page.goto(job["url"], wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        await _smart_fill_page(page, profile, tailored)
        submit = page.locator("button[type='submit'], input[type='submit']").first
        if await submit.is_visible(timeout=2000):
            await submit.click()
            await page.wait_for_timeout(3000)
            return True, "applied"
        return False, "no_submit_button"
    except Exception as e:
        return False, str(e)[:80]
    finally:
        await page.close()


# ── Main apply loop ────────────────────────────────────────────────────────────

async def _run_apply_loop(jobs: list[dict], profile: dict) -> list[dict]:
    results = []
    if not jobs:
        return results

    name_parts = _split_name(profile)
    profile.setdefault("full_name", f"{name_parts[0]} {name_parts[1]}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=HEADLESS)

        li_context: Optional[BrowserContext] = None
        has_linkedin = any(detect_ats(j["url"]) == "linkedin" for j in jobs)
        if has_linkedin and LINKEDIN_EMAIL:
            li_context = await browser.new_context()
            logged_in = await _linkedin_login(li_context)
            if not logged_in:
                logger.warning("LinkedIn login failed — LinkedIn jobs will be manual")
                await li_context.close()
                li_context = None

        for job in jobs:
            ats = detect_ats(job["url"])
            result = {
                "job_id":           job["job_id"],
                "title":            job["title"],
                "company":          job["company"],
                "url":              job["url"],
                "ats":              ats,
                "status":           "pending",
                "notes":            "",
                "cover_letter":     "",
                "keywords_matched": [],
            }

            if ats in ("workday", "icims", "jobvite", "smartrecruiters"):
                result["status"] = "requires_manual"
                result["notes"]  = f"{ats}_not_automated"
                results.append(result)
                continue

            try:
                tailored = tailor_application(job, profile)
                result["cover_letter"]     = tailored["cover_letter"]
                result["keywords_matched"] = tailored["keywords_matched"]
            except Exception as e:
                logger.warning("Tailoring failed for %s: %s", job["title"], e)
                tailored = {"cover_letter": "", "tailored_summary": "",
                            "tailored_bullets": [], "keywords_matched": []}

            try:
                ctx = await browser.new_context()
                if ats == "linkedin":
                    if li_context:
                        success, notes = await _linkedin_easy_apply(li_context, job, tailored, profile)
                    else:
                        success, notes = False, "linkedin_not_logged_in"
                elif ats == "greenhouse":
                    success, notes = await _apply_greenhouse(ctx, job, tailored, profile)
                elif ats == "lever":
                    success, notes = await _apply_lever(ctx, job, tailored, profile)
                elif ats == "ashby":
                    success, notes = await _apply_ashby(ctx, job, tailored, profile)
                else:
                    success, notes = await _apply_generic(ctx, job, tailored, profile)
                await ctx.close()

                result["status"] = "applied" if success else "failed"
                result["notes"]  = notes
            except Exception as e:
                result["status"] = "failed"
                result["notes"]  = str(e)[:80]
                logger.error("Apply error for %s: %s", job["title"], e)

            results.append(result)
            await asyncio.sleep(2)

        if li_context:
            await li_context.close()
        await browser.close()

    return results


def apply_to_jobs(jobs: list[dict], profile: dict) -> list[dict]:
    return asyncio.run(_run_apply_loop(jobs, profile))
