import urllib.parse
import re


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


def _extract_relevant_experience(profile: dict, job_desc: str = "") -> str:
    """Extract most relevant experience from profile, prioritized by job match."""
    experience = profile.get("experience") or ""
    skills = profile.get("skills") or []
    education = profile.get("education") or ""
    summary = profile.get("summary") or ""

    job_desc_lower = (job_desc or "").lower()
    skill_matches = []
    if job_desc and skills:
        for skill in skills:
            if skill.lower() in job_desc_lower:
                skill_matches.append(skill)

    parts = []
    if experience:
        exp_lines = experience.split("\n")
        relevant_exp = []
        for line in exp_lines[:3]:
            line = line.strip()
            if line and len(line) > 20:
                relevant_exp.append(line)
        if relevant_exp:
            parts.append(" ".join(relevant_exp[:2]))

    if skill_matches:
        parts.append(f"Core technologies: {', '.join(skill_matches[:6])}")

    if summary and len(summary) > 30:
        parts.append(summary[:200])

    return " ".join(parts)


def build_body(job: dict, profile: dict) -> str:
    name = profile.get("name") or "Applicant"
    phone = profile.get("phone") or ""
    email = profile.get("email") or ""
    linkedin = profile.get("linkedin") or ""
    github = profile.get("github") or ""
    portfolio = profile.get("portfolio") or ""

    title = job.get("title") or "the position"
    company = job.get("company") or "your team"
    location = job.get("location") or ""
    job_desc = job.get("description") or job.get("requirements") or ""

    location_str = f" in {location}" if location else ""

    exp_text = _extract_relevant_experience(profile, job_desc)
    skill_matches = []
    skills = profile.get("skills") or []
    if job_desc and skills:
        job_desc_lower = job_desc.lower()
        skill_matches = [s for s in skills if s.lower() in job_desc_lower]

    para1 = (
        f"Dear Hiring Manager,\n\n"
        f"I'm applying for the {title} role at {company}{location_str}. "
        f"The opportunity to work on "
        f"{job_desc[:120].strip() if job_desc else 'scalable backend systems and modern cloud infrastructure'} "
        f"aligns well with my background."
    )

    if skill_matches:
        tech_str = ", ".join(skill_matches[:5])
    else:
        tech_str = ", ".join(skills[:5]) if skills else "Python, JavaScript, cloud platforms"

    para2 = (
        f"\n\nI bring hands-on experience with {tech_str}. "
        f"{exp_text if exp_text else 'In recent roles I\'ve built production APIs, optimized database performance, and deployed containerized services on AWS/GCP.'} "
        f"My focus is on writing maintainable code, reducing deployment friction, and collaborating closely with product teams."
    )

    para3 = (
        f"\n\nI'd welcome the chance to discuss how I can contribute to {company}. "
        f"My resume is attached — thank you for your time.\n\n"
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
