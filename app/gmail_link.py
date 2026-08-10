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


def build_body(job: dict, profile: dict) -> str:
    name = profile.get("name") or "Applicant"
    phone = profile.get("phone") or ""
    email = profile.get("email") or ""
    linkedin = profile.get("linkedin") or ""
    github = profile.get("github") or ""
    portfolio = profile.get("portfolio") or ""
    skills = profile.get("skills") or []
    skills_str = ", ".join(skills[:8])

    title = job.get("title") or "the position"
    company = job.get("company") or "your team"
    location = job.get("location") or ""

    lines = [
        f"Dear Hiring Manager,",
        "",
        f"I am writing to express my interest in the {title} role at {company}"
        + (f" ({location})." if location else "."),
        "",
    ]

    if skills_str:
        lines.append(f"With experience in {skills_str}, I am confident I can contribute meaningfully to your team.")

    if portfolio:
        lines.append("")
        lines.append(f"Portfolio: {portfolio}")

    lines += [
        "",
        "I would welcome the opportunity to discuss how my background aligns with your needs. Please find my resume attached.",
        "",
        "Thank you for your consideration.",
        "",
        f"Best regards,",
        f"{name}",
    ]
    if phone:
        lines.append(f"{phone}")
    if email:
        lines.append(f"{email}")
    if linkedin:
        lines.append(f"LinkedIn: {linkedin}")
    if github:
        lines.append(f"GitHub: {github}")

    return "\n".join(lines)


def build_job_gmail_link(job: dict, profile: dict) -> str:
    subject = build_subject(job)
    body = build_body(job, profile)
    to = job.get("hr_email") or ""
    return build_gmail_link(to, subject, body)
