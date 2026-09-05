"""AI Studio — Gemini-powered CV tailoring with recommendations."""

import json

from app.gemini import generate_json, gemini_available


AI_STUDIO_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "skills": {"type": "array", "items": {"type": "string"}},
        "experience": {"type": "string"},
        "education": {"type": "string"},
        "custom_sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["title", "content"],
            },
        },
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "section": {"type": "string"},
                    "action": {"type": "string"},
                    "explanation": {"type": "string"},
                    "original": {"type": "string"},
                    "tailored": {"type": "string"},
                },
                "required": ["section", "action", "explanation", "original", "tailored"],
            },
        },
    },
    "required": ["summary", "skills", "experience", "education", "recommendations"],
}

AI_STUDIO_PROMPT = """You are an expert ATS resume optimizer. Given a job posting and an applicant's CV profile, produce a tailored resume optimized for THIS specific job.

Job posting:
TITLE: {job_title}
COMPANY: {company}
DESCRIPTION/SNIPPET: {job_snippet}
ROLE: {job_role}

Applicant's base CV profile:
{profile_json}

Instructions:
1. Rewrite the summary (2-3 sentences) to mirror keywords from the job posting. Keep it honest — do not fabricate experience.
2. Reorder and refine skills so the most relevant ones come first. Include exact terms from the job posting when they genuinely match. Max 15 skills.
3. Rewrite experience bullet points to echo the posting's language (never invent roles/dates/companies).
4. Keep education unchanged unless the job specifically requires something different.
5. If the job posting mentions tools/technologies the applicant clearly has experience with (visible in their profile), add a "Projects" or "Relevant Projects" custom section highlighting those.
6. For each change, create a recommendation entry explaining what you changed and why.

IMPORTANT: The "original" field in each recommendation should contain the EXACT text from the base profile that was changed. The "tailored" field should contain the new text.

Return ONLY valid JSON matching:
{AI_STUDIO_SCHEMA}"""


def generate_tailored_cv(job: dict, profile: dict) -> dict:
    """Generate tailored CV content + recommendations for a job.

    Returns dict with: summary, skills, experience, education, custom_sections, recommendations.
    Falls back to base profile content if Gemini is unavailable.
    """
    base_fallback = {
        "summary": profile.get("summary") or "",
        "skills": profile.get("skills") or [],
        "experience": profile.get("experience") or "",
        "education": profile.get("education") or "",
        "custom_sections": [],
        "recommendations": [],
    }

    if not gemini_available():
        return base_fallback

    prompt = AI_STUDIO_PROMPT.format(
        job_title=job.get("title") or "",
        company=job.get("company") or "",
        job_snippet=(job.get("snippet") or "")[:2000],
        job_role=job.get("role") or "",
        profile_json=json.dumps(profile, indent=2),
        AI_STUDIO_SCHEMA=json.dumps(AI_STUDIO_SCHEMA, indent=2),
    )

    try:
        data = generate_json(prompt, temperature=0.4)
    except Exception as e:
        print(f"  [ai-studio] Gemini generation failed ({e}); using base profile")
        return base_fallback

    skills = data.get("skills") or []
    if not isinstance(skills, list):
        skills = []

    recommendations = data.get("recommendations") or []
    if not isinstance(recommendations, list):
        recommendations = []

    custom_sections = data.get("custom_sections") or []
    if not isinstance(custom_sections, list):
        custom_sections = []

    return {
        "summary": str(data.get("summary") or "") or base_fallback["summary"],
        "skills": [str(s).strip() for s in skills if str(s).strip()] or base_fallback["skills"],
        "experience": str(data.get("experience") or "") or base_fallback["experience"],
        "education": str(data.get("education") or "") or base_fallback["education"],
        "custom_sections": custom_sections,
        "recommendations": recommendations,
    }
