import json
import re
import urllib.parse


def build_gmail_link(to: str, subject: str, body: str) -> str:
    params = {
        "view": "cm",
        "to": to or "",
        "su": subject,
        "body": body,
    }
    return "https://mail.google.com/mail/?" + urllib.parse.urlencode(
        params, quote_via=urllib.parse.quote
    )


def build_subject(job: dict) -> str:
    title = job.get("title") or "the open position"
    company = job.get("company") or ""
    if company:
        return f"Application for {title} at {company}"
    return f"Application for {title}"


def _normalize_skills(skills) -> list:
    if not skills:
        return []
    if isinstance(skills, str):
        return [s.strip() for s in skills.split(",") if s.strip()]
    return [str(s).strip() for s in skills if str(s).strip()]


_SECTION_HEADERS = {
    "requirements", "education", "experience", "responsibilities", "skills",
    "expertise", "compensation", "benefits", "job description", "about us",
    "about the role", "company", "location", "salary", "summary", "overview",
    "job highlights", "read before apply", "apply procedure",
    "additional requirements", "responsibilities & context", "job context",
    "employment status", "workplace",
}

_TITLE_PATTERNS = [
    re.compile(r"(?:job\s*title|position|role|designation|title)\s*[:\-]\s*([^\n]{3,70})", re.I),
    re.compile(r"\bseeking\s+a(?:n)?\s+([^\n]{3,70}?)\s+(?:to|who|for|that|with)\b", re.I),
    re.compile(r"\bhiring\s+a(?:n)?\s+([^\n]{3,70}?)\s+(?:to|who|for|that|with)\b", re.I),
    re.compile(r"\brecruiting\s+a(?:n)?\s+([^\n]{3,70}?)\s+(?:to|who|for|that|with)\b", re.I),
]

_COMPANY_PAT = re.compile(
    r"\b([A-Z][A-Za-z0-9&.\-]+(?:[ \t]+[A-Z][A-Za-z0-9&.\-]+){0,3})[ \t]+"
    r"(Ltd|Limited|Inc|LLC|PLC|Group|Corporation|Corp|Pvt|Private|Solutions|Systems)\b\.?"
)


def _company_from_email(email: str) -> str:
    """Best-effort company name from an HR email domain (empty for public mail)."""
    if not email or "@" not in email:
        return ""
    domain = email.split("@", 1)[1].lower()
    if domain in {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "live.com",
                  "icloud.com", "aol.com", "proton.me", "protonmail.com", "gmx.com"}:
        return ""
    sld = domain.split(".")[0]
    sld = re.sub(r"(hr|careers?|jobs?|recruit(?:ment)?|info|contact|talent|hiring|apply|talentacquisition)",
                 "", sld)
    sld = sld.strip(" -_")
    return sld.capitalize() if sld else ""


def _trim_words(text: str, limit: int) -> str:
    """Trim to <=limit chars on a word boundary (adds an ellipsis if cut)."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;")
    return cut + "…"


def _looks_like_header(line: str) -> bool:
    return line.strip().lower().rstrip(":").strip() in _SECTION_HEADERS


def _infer_title(text: str) -> str:
    for pat in [
        re.compile(r"(?:job\s*title|position|role|designation|title)\s*[:\-]\s*([^\n]{3,70})", re.I),
        re.compile(r"\bseeking\s+a(?:n)?\s+([^\n]{3,70}?)\s+(?:to|who|for|that|with)\b", re.I),
        re.compile(r"\bhiring\s+a(?:n)?\s+([^\n]{3,70}?)\s+(?:to|who|for|that|with)\b", re.I),
        re.compile(r"\brecruiting\s+a(?:n)?\s+([^\n]{3,70}?)\s+(?:to|who|for|that|with)\b", re.I),
    ]:
        m = pat.search(text or "")
        if m:
            t = m.group(1).strip().strip('."\'')
            if 3 <= len(t) <= 70 and not _looks_like_header(t):
                return t
    for line in (text or "").splitlines():
        line = line.strip()
        if (4 <= len(line) <= 70 and "@" not in line and "http" not in line
                and not line.lower().startswith("dear") and not _safe_header(line)):
            return line
    return ""


def _safe_header(line: str) -> bool:
    return _looks_like_header(line)


def _infer_company(text: str, email: str) -> str:
    for line in (text or "").splitlines():
        m = _COMPANY_PAT.search(line)
        if m:
            name = (m.group(1).strip() + " " + m.group(2)).title()
            name = name.replace("Ltd.", "Ltd").replace("Pvt.", "Pvt").replace("Inc.", "Inc")
            return name
    return _company_from_email(email)


_MATCHED_SKILLS = []


def _matched_skills(skills: list, job_desc: str) -> list:
    """Skills relevant to the posting (word-boundary match; skip 1-char skills)."""
    if not job_desc:
        return []
    jd = job_desc.lower()
    out = []
    for s in skills:
        if len(s) < 2:
            continue
        if re.search(r"\b" + re.escape(s.lower()) + r"\b", jd):
            out.append(s)
    return out


def _infer_job_from_text(text: str, email: str) -> dict:
    """Turn pasted job-posting text into a job dict (title/company/description)."""
    return {
        "title": _infer_title(text),
        "company": _infer_company(text, email),
        "description": text or "",
    }


def build_body(job: dict, profile: dict) -> str:
    name = (profile.get("name") or "").strip() or "Applicant"
    phone = (profile.get("phone") or "").strip()
    email = (profile.get("email") or "").strip()
    linkedin = (profile.get("linkedin") or "").strip()
    github = (profile.get("github") or "").strip()
    portfolio = (profile.get("portfolio") or "").strip()

    title = (job.get("title") or "").strip() or "the position"
    company = (job.get("company") or "").strip()
    job_desc = (job.get("description") or job.get("requirements") or "").strip()

    skills = _normalize_skills(profile.get("skills"))
    summary = (profile.get("summary") or "").strip()
    experience = (profile.get("experience") or "").strip()
    education = (profile.get("education") or "").strip()

    # Extract relevant skills from the job description
    if job_desc and skills:
        jd_lower = job_desc.lower()
        matched_skills = [s for s in skills if s.lower() in jd_lower]
    else:
        matched_skills = []
    skill_str = ", ".join(matched_skills[:6]) if matched_skills else ", ".join(_normalize_skills(profile.get("skills"))[:6])

    # Build a concise, professional highlight from the profile
    qual = []
    if summary:
        qual.append(_trim_words(summary, 220))
    elif experience:
        for line in experience.split("\n"):
            line = line.strip()
            if len(line) > 25:
                qual.append(_trim_words(line, 220))
                break
    if len(qual) < 2 and education:
        qual.append(f"Academic background: {_trim_words(education, 140)}")

    company_str = f" at {company}" if company else ""
    para1 = (
        f"Dear Hiring Manager,\n\n"
        f"I am writing to apply for the {title} role{company_str}. "
        f"I have reviewed the responsibilities and believe my background is a strong match "
        f"for what your team is looking for."
    )

    para2 = ""
    if skill_str:
        para2 = f"\n\nMy core strengths include {skill_str}. "
    if qual:
        para2 += " ".join(qual)

    para3 = (
        f"\n\nI have attached my resume and would welcome the chance to discuss how I can "
        f"contribute to your team. "
        f"Thank you for your time and consideration.\n\n"
        f"Best regards,\n{name}"
    )

    body = para1 + para2 + para3
    if phone:
        body += f"\n{phone}"
    if email:
        body += f"\n{email}"
    if linkedin:
        body += f"\nLinkedIn: {linkedin}"
    if github:
        body += f"\nGitHub: {github}"
    if portfolio:
        body += f"\nPortfolio: {portfolio}"

    return body


def build_job_gmail_link(job: dict, profile: dict) -> str:
    subject = build_subject(job)
    body = build_body(job, profile)
    to = job.get("hr_email") or ""
    return build_gmail_link(to, subject, body)