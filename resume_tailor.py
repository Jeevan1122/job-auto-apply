from __future__ import annotations

"""
Tailors cover letter and resume highlights for each specific job JD.
Goal: make the application look like it was written just for that role,
maximising keyword match so it passes ATS and gets a human to read it.
"""
import json
from openai import OpenAI
from config import GEMINI_API_KEY, GEMINI_BASE_URL, TAILOR_MODEL

_client = OpenAI(api_key=GEMINI_API_KEY, base_url=GEMINI_BASE_URL)

# ── Cover letter ───────────────────────────────────────────────────────────────

_COVER_LETTER_PROMPT = """You are an expert career coach writing a cover letter for a job applicant.

Write a concise, compelling cover letter (3 short paragraphs, under 220 words) for this job.
Rules:
- Opening: Show excitement for THIS specific company and role (use their name)
- Middle: Match 3-4 specific skills/experiences from the candidate profile to the JD requirements
- Closing: Clear call to action for an interview
- Tone: Professional but human — NOT generic
- Do NOT include headers, date, address, or sign-off — just the 3 paragraphs

Job Details:
Title: {title}
Company: {company}
Location: {location}
Job Description:
{jd}

Candidate Profile:
Current Title: {current_title}
Years of Experience: {years_exp}
Key Skills: {skills}
Summary: {summary}
"""

def generate_cover_letter(job: dict, profile: dict) -> str:
    skills_tech = profile.get("skills", {}).get("technical", [])[:10]
    skills_soft = profile.get("skills", {}).get("soft", [])[:5]
    all_skills  = ", ".join(skills_tech + skills_soft)

    prompt = _COVER_LETTER_PROMPT.format(
        title        = job.get("title", ""),
        company      = job.get("company", ""),
        location     = job.get("location", ""),
        jd           = (job.get("description") or "")[:2000],
        current_title = profile.get("current_title", "Professional"),
        years_exp    = profile.get("years_of_experience", ""),
        skills       = all_skills,
        summary      = profile.get("summary", ""),
    )
    resp = _client.chat.completions.create(
        model       = TAILOR_MODEL,
        messages    = [{"role": "user", "content": prompt}],
        temperature = 0.7,
        max_tokens  = 500,
    )
    return resp.choices[0].message.content.strip()


# ── Resume bullet tailoring ────────────────────────────────────────────────────

_TAILOR_BULLETS_PROMPT = """You are an expert resume writer.

Rewrite the candidate's professional summary and top 4 bullet points to best match this specific job.
Use keywords from the job description so the resume passes ATS screening.
Keep it truthful — only use skills and experiences already in the candidate profile.

Return ONLY a JSON object:
{{
  "summary": "One sentence professional summary tailored to this role",
  "bullets": [
    "Achievement bullet 1 with metrics if possible",
    "Achievement bullet 2",
    "Achievement bullet 3",
    "Achievement bullet 4"
  ],
  "keywords_matched": ["keyword1", "keyword2", "keyword3"]
}}

Job Title: {title}
Company: {company}
Job Description:
{jd}

Candidate Profile:
{profile_json}
"""

def tailor_resume_bullets(job: dict, profile: dict) -> dict:
    prompt = _TAILOR_BULLETS_PROMPT.format(
        title        = job.get("title", ""),
        company      = job.get("company", ""),
        jd           = (job.get("description") or "")[:2000],
        profile_json = json.dumps({
            "current_title":      profile.get("current_title"),
            "years_of_experience": profile.get("years_of_experience"),
            "skills":             profile.get("skills", {}),
            "summary":            profile.get("summary"),
            "keywords":           profile.get("keywords", []),
        }, indent=2),
    )
    resp = _client.chat.completions.create(
        model                = TAILOR_MODEL,
        messages             = [{"role": "user", "content": prompt}],
        temperature          = 0.3,
        max_tokens           = 600,
        response_format      = {"type": "json_object"},
    )
    try:
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return {"summary": "", "bullets": [], "keywords_matched": []}


# ── Combined tailor ────────────────────────────────────────────────────────────

def tailor_application(job: dict, profile: dict) -> dict:
    """
    Returns everything needed to submit a tailored application:
    {
        cover_letter: str,
        tailored_summary: str,
        tailored_bullets: list[str],
        keywords_matched: list[str],
    }
    """
    cover   = generate_cover_letter(job, profile)
    bullets = tailor_resume_bullets(job, profile)
    return {
        "cover_letter":      cover,
        "tailored_summary":  bullets.get("summary", ""),
        "tailored_bullets":  bullets.get("bullets", []),
        "keywords_matched":  bullets.get("keywords_matched", []),
    }
