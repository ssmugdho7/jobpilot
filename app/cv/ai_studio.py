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


# ---------------------------------------------------------------------------
# Typed suggestions (atomic patches)
# ---------------------------------------------------------------------------

SUGGESTION_KINDS = ("add_skill", "rewrite_summary", "rewrite_bullet", "add_keyword", "add_section")
TAILORABLE_SECTIONS = ("summary", "skills", "experience", "custom")
DEFAULT_SCOPE_SECTIONS = ["summary", "skills", "experience"]

MAX_LEN = {
    "summary": 600,
    "bullet": 400,
    "skill": 60,
    "section_body": 1200,
}


SUGGESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": list(SUGGESTION_KINDS)},
                    "section_key": {"type": "string"},
                    "title": {"type": "string"},
                    "before_value": {"type": "string"},
                    "after_value": {"type": "string"},
                    "experience_index": {"type": "integer"},
                    "bullet_index": {"type": "integer"},
                },
                "required": ["kind", "section_key", "title", "after_value"],
            },
        }
    },
    "required": ["suggestions"],
}

SUGGESTION_PROMPT = """You are an ATS resume optimizer. Produce ONLY atomic, independently-appliable suggestions for the resume sections visible below.

Job posting:
TITLE: {job_title}
COMPANY: {company}
DESCRIPTION/SNIPPET: {job_snippet}
ROLE: {job_role}

Current resume content (JSON):
{content_json}

Scope (sections the user allows changing):
{scope_sections}

Rules:
- Each suggestion must be a small, focused patch.
- kind must be one of: add_skill, rewrite_summary, rewrite_bullet, add_keyword, add_section.
- section_key must be one of the visible sections.
- For rewrite_bullet, include experience_index and bullet_index so we know which bullet to replace.
- For add_section, include after_value with the full new section content (JSON string with title and body).
- before_value must contain the EXACT text being replaced (or "" for additions).
- after_value must contain the new text.
- Do NOT invent credentials, dates, or companies.
- Max {max_suggestions} suggestions.

Return ONLY valid JSON matching:
{SUGGESTION_SCHEMA}"""

CUSTOM_SUGGESTION_PROMPT = """You are an ATS resume assistant. The user gave this instruction:

"{instruction}"

Current resume content (JSON):
{content_json}

Visible sections:
{scope_sections}

Rules:
- Produce ONLY atomic, independently-appliable suggestions.
- kind must be one of: add_skill, rewrite_summary, rewrite_bullet, add_keyword, add_section.
- section_key must be one of the visible sections.
- For rewrite_bullet, include experience_index and bullet_index.
- For add_section, include after_value with the full new section content.
- before_value must contain the EXACT text being replaced (or "" for additions).
- after_value must contain the new text.
- Do NOT invent credentials, dates, or companies.
- Max {max_suggestions} suggestions.

Return ONLY valid JSON matching:
{SUGGESTION_SCHEMA}"""


def normalize_scope(scope: dict) -> dict:
    sections = scope.get("sections") or DEFAULT_SCOPE_SECTIONS
    if isinstance(sections, str):
        sections = [s.strip() for s in sections.split(",") if s.strip()]
    sections = [s for s in sections if s in TAILORABLE_SECTIONS]
    if not sections:
        sections = list(DEFAULT_SCOPE_SECTIONS)

    return {
        "sections": sections,
        "bullets": bool(scope.get("bullets", True)),
        "allow_add_section": bool(scope.get("allow_add_section", True)),
    }


def scoped_content(content: dict, scope: dict) -> dict:
    visible_sections = set(scope["sections"])
    out = dict(content)

    if "experience" in out and isinstance(out["experience"], list) and not scope.get("bullets"):
        out["experience"] = [
            {
                "company": e.get("company", ""),
                "title": e.get("title", ""),
                "location": e.get("location", ""),
                "start_date": e.get("start_date", ""),
                "end_date": e.get("end_date", ""),
                "bullets": ["(locked — bullet-level edits disabled)"],
            }
            for e in out["experience"]
        ]

    if not scope.get("allow_add_section", True):
        out.pop("custom_sections", None)

    return out


def editable_summary(scope: dict) -> str:
    return ", ".join(scope.get("sections", DEFAULT_SCOPE_SECTIONS))


def _numbers_supported(text: str) -> bool:
    return not bool(re.search(r"\\$\\d", text))


def _seed_numbers(text: str) -> str:
    return text


def generate_suggestions(job: dict, content: dict, scope: dict, max_suggestions: int = 8) -> dict:
    if not gemini_available():
        return {"suggestions": []}

    prompt = SUGGESTION_PROMPT.format(
        job_title=job.get("title") or "",
        company=job.get("company") or "",
        job_snippet=(job.get("snippet") or "")[:2000],
        job_role=job.get("role") or "",
        content_json=json.dumps(content, indent=2),
        scope_sections=editable_summary(scope),
        max_suggestions=max_suggestions,
        SUGGESTION_SCHEMA=json.dumps(SUGGESTION_SCHEMA, indent=2),
    )

    try:
        data = generate_json(prompt, temperature=0.4)
    except Exception as e:
        print(f"  [ai-studio] suggestion generation failed ({e})")
        return {"suggestions": []}

    if not isinstance(data, dict):
        return {"suggestions": []}

    raw = data.get("suggestions") or []
    if not isinstance(raw, list):
        return {"suggestions": []}

    cleaned = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind", "")
        if kind not in SUGGESTION_KINDS:
            continue
        section_key = item.get("section_key", "")
        if section_key not in scope.get("sections", []):
            continue
        after_value = str(item.get("after_value", "") or "")
        if not after_value:
            continue
        if len(after_value) > MAX_LEN.get("section_body", 1200):
            continue
        if not _numbers_supported(after_value):
            continue
        cleaned.append({
            "kind": kind,
            "section_key": section_key,
            "title": str(item.get("title", "") or kind),
            "before_value": str(item.get("before_value", "") or ""),
            "after_value": after_value,
            "experience_index": item.get("experience_index"),
            "bullet_index": item.get("bullet_index"),
        })
    return {"suggestions": cleaned}


def validate_suggestions(items: list, scope: dict, content: dict) -> tuple:
    valid = []
    rejected = []
    seen = set()

    for item in items:
        key = (item.get("kind"), item.get("section_key"), item.get("after_value", "")[:80])
        if key in seen:
            rejected.append({"item": item, "reason": "duplicate"})
            continue
        seen.add(key)

        if item.get("kind") not in SUGGESTION_KINDS:
            rejected.append({"item": item, "reason": "unknown kind"})
            continue
        if item.get("section_key") not in scope.get("sections", []):
            rejected.append({"item": item, "reason": "out of scope"})
            continue

        after = item.get("after_value", "")
        if not after:
            rejected.append({"item": item, "reason": "empty after_value"})
            continue

        if item.get("kind") == "rewrite_bullet":
            try:
                ei = int(item.get("experience_index", -1))
                bi = int(item.get("bullet_index", -1))
            except (TypeError, ValueError):
                rejected.append({"item": item, "reason": "bad indices"})
                continue
            exp_list = content.get("experience", [])
            if not isinstance(exp_list, list) or ei < 0 or ei >= len(exp_list):
                rejected.append({"item": item, "reason": "bad experience_index"})
                continue
            bullets = exp_list[ei].get("bullets", [])
            if not isinstance(bullets, list) or bi < 0 or bi >= len(bullets):
                rejected.append({"item": item, "reason": "bad bullet_index"})
                continue
            before = item.get("before_value", "")
            if before and bullets[bi] != before:
                rejected.append({"item": item, "reason": "before_value mismatch"})
                continue

        valid.append(item)

    return valid, rejected


def apply_suggestion_patch(content: dict, suggestion: dict) -> bool:
    kind = suggestion.get("kind")
    section_key = suggestion.get("section_key")
    after_value = suggestion.get("after_value", "")

    if kind == "add_skill":
        skills = content.get("skills") or []
        if not isinstance(skills, list):
            skills = []
        if after_value and after_value not in skills:
            skills.append(after_value)
            content["skills"] = skills
            return True
        return False

    if kind == "add_keyword":
        skills = content.get("skills") or []
        if not isinstance(skills, list):
            skills = []
        if after_value and after_value not in skills:
            skills.append(after_value)
            content["skills"] = skills
            return True
        return False

    if kind == "rewrite_summary":
        if section_key in content and after_value:
            content[section_key] = after_value
            return True
        return False

    if kind == "rewrite_bullet":
        experience = content.get("experience") or []
        if not isinstance(experience, list):
            return False
        try:
            ei = int(suggestion.get("experience_index", -1))
            bi = int(suggestion.get("bullet_index", -1))
        except (TypeError, ValueError):
            return False
        if 0 <= ei < len(experience):
            bullets = experience[ei].get("bullets") or []
            if isinstance(bullets, list) and 0 <= bi < len(bullets):
                bullets[bi] = after_value
                experience[ei]["bullets"] = bullets
                content["experience"] = experience
                return True
        return False

    if kind == "add_section":
        custom_sections = content.get("custom_sections") or []
        if not isinstance(custom_sections, list):
            custom_sections = []
        try:
            section_data = json.loads(after_value) if after_value else {}
        except json.JSONDecodeError:
            section_data = {"title": after_value, "content": ""}
        section_data.setdefault("id", section_data.get("title", "custom").lower().replace(" ", "_"))
        section_data.setdefault("title", "Custom Section")
        section_data.setdefault("content", "")
        custom_sections.append(section_data)
        content["custom_sections"] = custom_sections
        return True

    return False


def generate_custom_suggestions(instruction: str, content: dict, scope: dict, max_suggestions: int = 6) -> dict:
    if not gemini_available() or not instruction.strip():
        return {"suggestions": []}

    prompt = CUSTOM_SUGGESTION_PROMPT.format(
        instruction=instruction.strip(),
        content_json=json.dumps(content, indent=2),
        scope_sections=editable_summary(scope),
        max_suggestions=max_suggestions,
        SUGGESTION_SCHEMA=json.dumps(SUGGESTION_SCHEMA, indent=2),
    )

    try:
        data = generate_json(prompt, temperature=0.4)
    except Exception as e:
        print(f"  [ai-studio] custom suggestion generation failed ({e})")
        return {"suggestions": []}

    if not isinstance(data, dict):
        return {"suggestions": []}

    raw = data.get("suggestions") or []
    valid, _ = validate_suggestions(raw, scope, content)
    return {"suggestions": valid}
