from __future__ import annotations

import io
import json
import re
from pathlib import Path

from openai import OpenAI
from pdfminer.high_level import extract_text as pdf_extract_text
from docx import Document

from config import GEMINI_API_KEY, GEMINI_BASE_URL, RESUME_PARSE_MODEL

_client: OpenAI | None = None

def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=GEMINI_API_KEY, base_url=GEMINI_BASE_URL)
    return _client

_PARSE_PROMPT = """You are a resume parsing assistant. Extract structured information from the resume text below.

Return ONLY a valid JSON object with these exact keys — no explanation, no markdown, just raw JSON:
{{
  "job_titles": ["list of job titles the candidate qualifies for"],
  "skills": {{
    "technical": ["Python", "React", "..."],
    "soft": ["communication", "leadership", "..."]
  }},
  "years_of_experience": 3,
  "industries": ["Software", "FinTech", "..."],
  "education": [{{"degree": "B.S. Computer Science", "school": "MIT", "year": 2020}}],
  "location_preference": "Remote / US",
  "current_title": "Senior Software Engineer",
  "summary": "One-paragraph professional summary",
  "keywords": ["backend", "API", "cloud", "..."]
}}

Resume text:
---
{resume_text}
---"""


def extract_text_from_pdf(file_bytes: bytes) -> str:
    return pdf_extract_text(io.BytesIO(file_bytes))


def extract_text_from_docx(file_bytes: bytes) -> str:
    doc = Document(io.BytesIO(file_bytes))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_raw_text(filename: str, file_bytes: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_bytes)
    elif ext in (".docx", ".doc"):
        return extract_text_from_docx(file_bytes)
    raise ValueError(f"Unsupported file type: {ext}. Upload PDF or DOCX.")


def _extract_json(text: str) -> dict:
    """Robustly extract a JSON object from the model response."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        try:
            return json.loads(brace.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError(
        f"Could not parse JSON from model response. First 300 chars: {text[:300]!r}"
    )


def parse_resume_with_openai(raw_text: str) -> dict:
    prompt = _PARSE_PROMPT.format(resume_text=raw_text[:12000])
    response = _get_client().chat.completions.create(
        model=RESUME_PARSE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def parse_resume(filename: str, file_bytes: bytes) -> tuple[str, dict]:
    """Returns (raw_text, parsed_profile_dict)."""
    raw_text = extract_raw_text(filename, file_bytes)
    if not raw_text or len(raw_text.strip()) < 50:
        raise ValueError("Could not extract readable text from the resume.")
    parsed = parse_resume_with_openai(raw_text)
    return raw_text, parsed
