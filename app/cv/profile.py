import json
import re

from app.cv.parse import extract_contact, first_line_name
from app.gemini import generate_json, gemini_available

SECTION_ALIASES = {
    "summary": ["professional summary", "summary", "profile", "about", "objective", "career objective", "overview", "career summary"],
    "experience": ["work experience", "professional experience", "experience", "employment", "work history", "internship", "internships"],
    "education": ["education", "academic", "academics", "qualification", "qualifications", "educational background"],
    "skills": ["technical skills", "skills", "core skills", "key skills", "technologies", "tools", "competencies", "tech stack"],
    "projects": ["projects", "personal projects", "key projects", "project experience", "notable projects"],
    "certifications": ["certifications", "certificates", "licenses", "professional certifications", "credentials"],
    "languages": ["languages", "foreign languages", "language skills", "linguistic skills"],
    "references": ["references", "professional references", "referees"],
}

PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "email": {"type": "string"},
        "phone": {"type": "string"},
        "linkedin": {"type": "string"},
        "github": {"type": "string"},
        "website": {"type": "string"},
        "portfolio": {"type": "string"},
        "summary": {"type": "string"},
        "education": {"type": "string"},
        "experience": {"type": "string"},
        "skills": {"type": "array", "items": {"type": "string"}},
        "projects": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "description": {"type": "string"}, "bullets": {"type": "array", "items": {"type": "string"}}}}},
        "certifications": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "issuer": {"type": "string"}, "date": {"type": "string"}}}},
        "languages": {"type": "array", "items": {"type": "object", "properties": {"language": {"type": "string"}, "proficiency": {"type": "string"}}}},
    },
    "required": ["name", "email", "phone", "linkedin", "github", "website", "portfolio",
                 "summary", "education", "experience", "skills"],
}

PROFILE_PROMPT = """You are a CV parsing assistant. Extract structured profile data from the CV text below.

Rules:
- name: the person's full name (first non-trivial line of the CV is a good hint, but verify).
- summary: 2-3 sentence professional summary in first person.
- experience: condensed work experience (role, company, key responsibilities) as readable text.
- education: degrees + institutions.
- skills: list of concrete technical skills (languages, frameworks, tools).
- website: personal website URL (not LinkedIn, GitHub, or portfolio).
- projects: list of projects with name, description, and bullet points if available.
- certifications: list of certifications with name, issuer, and date if available.
- languages: list of languages with proficiency level if available.
- If a field is absent, use empty string (or empty list for array fields).
- Do NOT invent information.

Return ONLY valid JSON matching this schema:
{PROFILE_SCHEMA}

CV TEXT:
===START===
{cv_text}
===END==="""


def _split_sections(text: str) -> dict:
    """Split CV text into sections by common heading lines (heuristic)."""
    lines = text.splitlines()
    sections: dict[str, list[str]] = {}
    current = None
    heading_pat = re.compile(r"^([A-Z][A-Za-z&/\- ]{2,40})$")

    for line in lines:
        stripped = line.strip().strip(":#;*-•").strip()
        if not stripped:
            continue
        low = stripped.lower()
        matched_heading = None
        for section, aliases in SECTION_ALIASES.items():
            if low in aliases and len(low) <= 40:
                matched_heading = section
                break
        if matched_heading is None and current is None and len(stripped) <= 45 and heading_pat.match(stripped):
            matched_heading = "summary"

        if matched_heading:
            current = matched_heading
            sections.setdefault(current, [])
        elif current:
            sections[current].append(stripped)
    return sections


def _fallback_profile(text: str, existing: dict | None = None) -> dict:
    contact = extract_contact(text)
    sections = _split_sections(text)

    def join(key: str) -> str:
        return "\n".join(sections.get(key, [])).strip()

    skills = []
    skills_text = join("skills")
    if skills_text:
        skills = [s.strip().rstrip(",;") for s in re.split(r"[,\n|]+", skills_text) if s.strip()]

    # Parse projects from sections
    projects = []
    projects_text = join("projects")
    if projects_text:
        blocks = [b.strip() for b in projects_text.split("\n\n") if b.strip()]
        if not blocks:
            blocks = [projects_text]
        for block in blocks:
            lines = block.split("\n")
            name = lines[0] if lines else ""
            description = " ".join(lines[1:]) if len(lines) > 1 else ""
            projects.append({"name": name, "description": description, "bullets": []})

    # Parse certifications from sections
    certifications = []
    certs_text = join("certifications")
    if certs_text:
        for line in certs_text.split("\n"):
            line = line.strip()
            if line:
                certifications.append({"name": line, "issuer": "", "date": ""})

    # Parse languages from sections
    languages = []
    langs_text = join("languages")
    if langs_text:
        for line in langs_text.split("\n"):
            line = line.strip()
            if line:
                parts = re.split(r"[-–—]", line, maxsplit=1)
                lang = parts[0].strip()
                prof = parts[1].strip() if len(parts) > 1 else ""
                languages.append({"language": lang, "proficiency": prof})

    fallback = {
        "name": first_line_name(text),
        "email": contact["email"],
        "phone": contact["phone"],
        "linkedin": contact["linkedin"],
        "github": contact["github"],
        "website": contact["website"],
        "portfolio": contact["portfolio"],
        "summary": join("summary"),
        "education": join("education"),
        "experience": join("experience"),
        "skills": skills,
        "projects": projects,
        "certifications": certifications,
        "languages": languages,
    }

    if existing:
        for k, v in existing.items():
            if v:
                fallback[k] = v
    return fallback


def profile_from_text(cv_text: str, existing: dict | None = None) -> dict:
    fallback = _fallback_profile(cv_text, existing)

    if not gemini_available():
        return fallback

    contact = extract_contact(cv_text)
    name = first_line_name(cv_text)

    prompt = PROFILE_PROMPT.format(
        PROFILE_SCHEMA=json.dumps(PROFILE_SCHEMA), cv_text=cv_text[:12000]
    )
    try:
        data = generate_json(prompt)
    except Exception as e:
        print(f"  [profile] Gemini parse failed ({e}); using regex fallback")
        return fallback

    for key in PROFILE_SCHEMA["properties"]:
        if key == "skills":
            skills = data.get("skills") or []
            if not isinstance(skills, list):
                skills = []
            fallback[key] = [str(s).strip() for s in skills if str(s).strip()]
        elif key in ("projects", "certifications", "languages"):
            # Handle array of objects
            items = data.get(key) or []
            if isinstance(items, list) and items:
                fallback[key] = items
        else:
            val = str(data.get(key, "") or "").strip()
            if val:
                fallback[key] = val

    # keep regex-extracted contact info as authoritative where Gemini missed it
    for k in ("email", "phone", "linkedin", "github", "website", "portfolio"):
        if not fallback[k]:
            fallback[k] = contact[k]
    if not fallback["name"]:
        fallback["name"] = name

    return fallback
