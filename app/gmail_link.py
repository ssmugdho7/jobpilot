import urllib.parse


def build_gmail_link(to: str, subject: str, body: str, attach_cv: bool = True) -> str:
    params = {
        "view": "cm",
        "fs": "1",
        "to": to or "",
        "su": subject,
        "body": body,
    }
    if attach_cv:
        params["attach"] = "1"
    return "https://mail.google.com/mail/?" + urllib.parse.urlencode(
        params, quote_via=urllib.parse.quote
    )


def build_subject(job: dict) -> str:
    title = job.get("title") or "the open position"
    company = job.get("company") or ""
    if company:
        return f"Application for {title} at {company}"
    return f"Application for {title}"


def build_body(job: dict, profile: dict) -> str:
    name = profile.get("name") or "Applicant"
    phone = profile.get("phone") or ""
    email = profile.get("email") or ""
    linkedin = profile.get("linkedin") or ""
    github = profile.get("github") or ""
    portfolio = profile.get("portfolio") or ""
    summary = profile.get("summary") or ""
    education = profile.get("education") or ""
    experience = profile.get("experience") or ""
    skills = profile.get("skills") or []
    skills_str = ", ".join(skills[:10])

    title = job.get("title") or "the position"
    company = job.get("company") or "your company"
    location = job.get("location") or ""

    links = []
    if linkedin:
        links.append(f"LinkedIn: {linkedin}")
    if github:
        links.append(f"GitHub: {github}")
    if portfolio:
        links.append(f"Portfolio: {portfolio}")
    links_str = "\n".join(links)

    lines = [
        f"Dear Hiring Manager,",
        "",
        f"I am writing to express my strong interest in the {title} position at {company}"
        + (f", located in {location}." if location else "."),
        "",
    ]
    if summary:
        lines.append(summary)
        lines.append("")
    lines.append(f"My technical skills include: {skills_str}.")
    if experience:
        lines.append(f"")
        lines.append(f"Experience: {experience}")
    if education:
        lines.append("")
        lines.append(f"Education: {education}.")
    lines += [
        "",
        "I have attached my CV for your review. I would welcome the opportunity to discuss how my skills and enthusiasm can contribute to your team.",
        "",
        "Thank you for your time and consideration.",
        "",
        "Best regards,",
        name,
    ]
    if phone:
        lines.append(f"Phone: {phone}")
    if email:
        lines.append(f"Email: {email}")
    if links_str:
        lines.append(links_str)

    return "\n".join(lines)


def build_job_gmail_link(job: dict, profile: dict, attach_cv: bool = True) -> str:
    subject = build_subject(job)
    body = build_body(job, profile)
    to = job.get("hr_email") or job.get("email") or ""
    return build_gmail_link(to, subject, body, attach_cv)
