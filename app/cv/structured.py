"""Convert flat parsed_profile into structured content JSON for AI Studio sessions."""

import json
import re

from app.gemini import generate_json, gemini_available


STRUCTURED_SCHEMA = {
    "type": "object",
    "properties": {
        "personal_info": {
            "type": "object",
            "properties": {
                "full_name": {"type": "string"},
                "job_title": {"type": "string"},
                "location": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string"},
                "website": {"type": "string"},
                "linkedin": {"type": "string"},
                "github": {"type": "string"},
                "photo_url": {"type": "string"},
            },
            "required": ["full_name"],
        },
        "summary": {"type": "string"},
        "skills": {"type": "array", "items": {"type": "string"}},
        "experience": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "title": {"type": "string"},
                    "location": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "bullets": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["company", "title", "bullets"],
            },
        },
        "education": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "school": {"type": "string"},
                    "degree": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "details": {"type": "string"},
                },
                "required": ["school", "degree"],
            },
        },
        "custom_sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["id", "title", "content"],
            },
        },
    },
    "required": ["personal_info", "summary", "skills", "experience", "education"],
}


STRUCTURED_PROMPT = """You are a CV structuring assistant. Convert the flat CV profile below into structured JSON.

Rules:
- personal_info: extract full_name, job_title, location, email, phone, website, linkedin, github from the profile fields.
- summary: keep the existing summary text.
- skills: return as a list of strings.
- experience: split the free-text experience blob into an array of entries. Each entry must have company, title, location (optional), start_date, end_date (optional), and bullets (array of strings, one per responsibility/achievement line). If you cannot reliably split the blob, return a single entry with the whole blob as the first bullet.
- education: split the free-text education blob into an array of entries. Each entry must have school, degree, start_date, end_date (optional), details (optional).
- custom_sections: empty array.
- Do NOT invent information not present in the source.

Return ONLY valid JSON matching this schema:
{STRUCTURED_SCHEMA}

SOURCE PROFILE:
{profile_json}"""


def _fallback_structured(profile: dict) -> dict:
    """Build structured content from a flat profile without Gemini."""
    skills = profile.get("skills") or []
    if not isinstance(skills, list):
        skills = [s.strip() for s in str(skills).split(",") if s.strip()]

    experience_text = profile.get("experience") or ""
    experience = []
    if experience_text:
        bullets = [ln.strip() for ln in experience_text.splitlines() if ln.strip()]
        if not bullets:
            bullets = [experience_text.strip()]
        experience.append({
            "company": profile.get("name") or "",
            "title": "",
            "location": "",
            "start_date": "",
            "end_date": "",
            "bullets": bullets,
        })

    education_text = profile.get("education") or ""
    education = []
    if education_text:
        education.append({
            "school": "",
            "degree": education_text.strip(),
            "start_date": "",
            "end_date": "",
            "details": "",
        })

    return {
        "personal_info": {
            "full_name": profile.get("name") or "",
            "job_title": profile.get("job_title") or "",
            "location": profile.get("location") or "",
            "email": profile.get("email") or "",
            "phone": profile.get("phone") or "",
            "website": profile.get("portfolio") or "",
            "linkedin": profile.get("linkedin") or "",
            "github": profile.get("github") or "",
            "photo_url": "",
        },
        "summary": profile.get("summary") or "",
        "skills": skills,
        "experience": experience,
        "education": education,
        "custom_sections": [],
    }


def profile_to_structured(profile: dict) -> dict:
    """Upgrade a flat parsed_profile into the structured content JSON shape.

    Uses Gemini to split experience/education blobs into structured entries.
    Falls back to a single-entry heuristic when Gemini is unavailable.
    """
    fallback = _fallback_structured(profile)

    if not gemini_available():
        return fallback

    prompt = STRUCTURED_PROMPT.format(
        STRUCTURED_SCHEMA=json.dumps(STRUCTURED_SCHEMA, indent=2),
        profile_json=json.dumps(profile, indent=2),
    )
    try:
        data = generate_json(prompt, temperature=0.2)
    except Exception as e:
        print(f"  [structured] Gemini parse failed ({e}); using fallback")
        return fallback

    if not isinstance(data, dict):
        return fallback

    skills = data.get("skills") or []
    if not isinstance(skills, list):
        skills = [s.strip() for s in str(skills).split(",") if s.strip()]

    experience = data.get("experience") or []
    if not isinstance(experience, list):
        experience = fallback["experience"]

    education = data.get("education") or []
    if not isinstance(education, list):
        education = fallback["education"]

    custom_sections = data.get("custom_sections") or []
    if not isinstance(custom_sections, list):
        custom_sections = []

    personal_info = data.get("personal_info") or {}
    if not isinstance(personal_info, dict):
        personal_info = fallback["personal_info"]

    return {
        "personal_info": {
            "full_name": str(personal_info.get("full_name") or fallback["personal_info"]["full_name"] or ""),
            "job_title": str(personal_info.get("job_title") or fallback["personal_info"]["job_title"] or ""),
            "location": str(personal_info.get("location") or fallback["personal_info"]["location"] or ""),
            "email": str(personal_info.get("email") or fallback["personal_info"]["email"] or ""),
            "phone": str(personal_info.get("phone") or fallback["personal_info"]["phone"] or ""),
            "website": str(personal_info.get("website") or fallback["personal_info"]["website"] or ""),
            "linkedin": str(personal_info.get("linkedin") or fallback["personal_info"]["linkedin"] or ""),
            "github": str(personal_info.get("github") or fallback["personal_info"]["github"] or ""),
            "photo_url": str(personal_info.get("photo_url") or ""),
        },
        "summary": str(data.get("summary") or fallback["summary"] or ""),
        "skills": [str(s).strip() for s in skills if str(s).strip()] or fallback["skills"],
        "experience": experience or fallback["experience"],
        "education": education or fallback["education"],
        "custom_sections": custom_sections,
    }
