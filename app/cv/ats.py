import json

from app.gemini import generate_json, gemini_available
from app.cv.profile import PROFILE_SCHEMA

ATS_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "skills": {"type": "array", "items": {"type": "string"}},
        "experience": {"type": "string"},
        "education": {"type": "string"},
    },
    "required": ["summary", "skills", "experience", "education"],
}

ATS_PROMPT = """You write ATS-friendly resumes tailored to a specific job posting.

Job posting:
TITLE: {job_title}
COMPANY: {company}
SNIPPET: {job_snippet}

Applicant's base profile (from their uploaded CV):
{profile_json}

Write an ATS-optimized resume section for THIS job:
- summary: 2-3 sentence professional summary that mirrors keywords from the job posting.
- skills: reorder/refine the applicant's skills so the most relevant to the posting come first; include exact terms from the posting when they genuinely match the applicant's experience. Max 15 skills.
- experience: keep the applicant's real experience but phrase bullet points to echo the posting's language (never invent roles/dates/companies).
- education: unchanged from profile.
- Output plain text only. No tables, columns, graphics, or markdown. Single column, standard section names.
- Be honest: do not fabricate credentials.

Return ONLY valid JSON matching:
{ATS_SCHEMA}"""


def generate_ats_cv(job: dict, profile: dict) -> dict:
    """Return dict with summary/skills/experience/education tailored to the job."""
    if not gemini_available():
        return {
            "summary": profile.get("summary") or "",
            "skills": profile.get("skills") or [],
            "experience": profile.get("experience") or "",
            "education": profile.get("education") or "",
        }

    prompt = ATS_PROMPT.format(
        job_title=job.get("title") or "",
        company=job.get("company") or "",
        job_snippet=(job.get("snippet") or "")[:1500],
        profile_json=json.dumps(profile),
        ATS_SCHEMA=json.dumps(ATS_SCHEMA),
    )
    try:
        data = generate_json(prompt, temperature=0.5)
    except Exception as e:
        print(f"  [ats] Gemini generation failed ({e}); using base profile")
        return {
            "summary": profile.get("summary") or "",
            "skills": profile.get("skills") or [],
            "experience": profile.get("experience") or "",
            "education": profile.get("education") or "",
        }

    skills = data.get("skills") or []
    if not isinstance(skills, list):
        skills = []
    return {
        "summary": str(data.get("summary", "") or ""),
        "skills": [str(s).strip() for s in skills if str(s).strip()],
        "experience": str(data.get("experience", "") or ""),
        "education": str(data.get("education", "") or ""),
    }
