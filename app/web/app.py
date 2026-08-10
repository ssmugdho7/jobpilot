import os
import re
import yaml
from datetime import datetime, timedelta
from urllib.parse import urlparse
from functools import wraps

from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, and_, or_

from app.db import SessionLocal, Job, Profile, User, UserJob, get_user_job, profile_to_dict, get_or_create_profile
from app.pipeline import run_scan_async, _clean_job
from app.cv.parse import extract_email
from app.gmail_link import build_job_gmail_link
from app.paths import CONFIG_DIR
from app.config import load_search_config

DAYS_OPTIONS = [("1", "1 day"), ("3", "3 days"), ("7", "1 week"), ("30", "1 month")]

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "jobpilot-super-secret-key-change-in-prod")

EMAIL_RE_PATTERN = r"[\w.+-]+@[\w-]+\.[\w.-]+"

# Emails that are NOT a real HR/person contact — skip for Gmail compose
JUNK_EMAILS = {
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "mailer-daemon", "postmaster", "bounce",
    "info", "support", "help", "admin", "webmaster",
    "notifications", "notification", "alerts", "marketing",
    "subscribe", "unsubscribe", "feedback",
}


def _is_useful_email(email: str) -> bool:
    if not email:
        return False
    local = email.split("@")[0].lower().replace(".", "").replace("-", "").replace("_", "")
    for junk in JUNK_EMAILS:
        if junk in local:
            return False
    return True


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""
        db_session = SessionLocal()
        try:
            user = db_session.query(User).filter_by(username=username).first()
            if user and check_password_hash(user.password_hash, password):
                session["user_id"] = user.id
                session["username"] = user.username
                return redirect(url_for("index"))
            return render_template("login.html", error="Invalid username or password")
        finally:
            db_session.close()
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    require_invite = bool(os.getenv("REGISTER_CODE", "").strip())
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""
        invite_code = request.form.get("invite_code") or ""

        if require_invite and invite_code != os.getenv("REGISTER_CODE", "").strip():
            return render_template("register.html", error="Invalid invite code", require_invite=True)
        if not username or not password:
            return render_template("register.html", error="Username and password required", require_invite=require_invite)

        db_session = SessionLocal()
        try:
            existing = db_session.query(User).filter_by(username=username).first()
            if existing:
                return render_template("register.html", error="Username already taken", require_invite=require_invite)
            user = User(username=username, password_hash=generate_password_hash(password))
            db_session.add(user)
            db_session.commit()
            session["user_id"] = user.id
            session["username"] = user.username
            return redirect(url_for("index"))
        finally:
            db_session.close()
    return render_template("register.html", require_invite=require_invite)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    status = request.args.get("status", "").strip()
    days = request.args.get("days", "1")
    page = request.args.get("page", "1")
    role_filter = request.args.get("role", "").strip().lower()
    try:
        days = int(days)
    except ValueError:
        days = 1
    if days not in (1, 3, 7, 30):
        days = 1
    try:
        page = int(page)
    except ValueError:
        page = 1
    if page < 1:
        page = 1
    cutoff = datetime.utcnow() - timedelta(days=days)
    user_id = session["user_id"]

    db_session = SessionLocal()
    try:
        q = db_session.query(Job)
        if role_filter:
            q = q.filter(Job.role == role_filter)
        q = q.filter((Job.posted_date.is_(None)) | (Job.posted_date >= cutoff))

        if status in ("applied", "dismissed"):
            q = q.join(UserJob, and_(UserJob.job_id == Job.id, UserJob.user_id == user_id, UserJob.status == status))
        elif status == "new":
            q = q.outerjoin(UserJob, and_(UserJob.job_id == Job.id, UserJob.user_id == user_id))
            q = q.filter(or_(UserJob.status == "new", UserJob.status.is_(None)))

        total = q.count()
        PER_PAGE = 20
        total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
        if page > total_pages:
            page = total_pages
        offset = (page - 1) * PER_PAGE
        jobs = q.order_by(Job.posted_date.desc()).offset(offset).limit(PER_PAGE).all()

        profile = get_or_create_profile(user_id, db_session)
        p_dict = profile_to_dict(profile)

        for job in jobs:
            uj = get_user_job(user_id, job.id, db_session)
            job.status = uj.status
            hr_email = getattr(job, "hr_email", "") or ""
            if _is_useful_email(hr_email):
                job.gmail_link = build_job_gmail_link(
                    {"title": job.title, "company": job.company, "location": job.location, "hr_email": hr_email},
                    p_dict,
                )
            else:
                job.gmail_link = ""

        search_cfg = load_search_config()
        return render_template(
            "index.html",
            jobs=jobs,
            active_status=status,
            active_days=days,
            active_role=role_filter,
            active_page=page,
            total_pages=total_pages,
            days_options=DAYS_OPTIONS,
            roles=search_cfg.get("roles", []),
            custom_roles=search_cfg.get("custom_roles", []),
            now=datetime.utcnow(),
            counts=_status_counts(db_session, user_id, cutoff),
            username=session.get("username"),
        )
    finally:
        db_session.close()


def _status_counts(db_session, user_id, cutoff) -> dict:
    base_q = db_session.query(Job).filter((Job.posted_date.is_(None)) | (Job.posted_date >= cutoff))
    total_jobs = base_q.count()

    subq = base_q.subquery()
    rows = db_session.query(UserJob.status, func.count(UserJob.job_id)).join(subq, UserJob.job_id == subq.c.id).filter(UserJob.user_id == user_id).group_by(UserJob.status).all()

    applied = 0
    dismissed = 0
    for st, cnt in rows:
        if st == "applied":
            applied = cnt
        elif st == "dismissed":
            dismissed = cnt
    new_count = max(0, total_jobs - applied - dismissed)
    return {
        "new": new_count,
        "applied": applied,
        "dismissed": dismissed,
        "all": total_jobs,
    }


@app.route("/profile")
@login_required
def profile_page():
    db_session = SessionLocal()
    try:
        profile = get_or_create_profile(session["user_id"], db_session)
        return render_template("profile.html", profile=profile_to_dict(profile), username=session.get("username"))
    finally:
        db_session.close()


@app.route("/api/scan", methods=["POST"])
@login_required
def api_scan():
    started = run_scan_async()
    if not started:
        return jsonify({"ok": True, "started": False, "error": "scan already running"}), 202
    return jsonify({"ok": True, "started": True})


@app.route("/api/jobs/<int:job_id>/status", methods=["POST"])
@login_required
def api_update_status(job_id):
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    if new_status not in ("new", "applied", "dismissed"):
        return jsonify({"error": "invalid status"}), 400
    db_session = SessionLocal()
    try:
        job = db_session.query(Job).get(job_id)
        if not job:
            return jsonify({"error": "not found"}), 404
        uj = get_user_job(session["user_id"], job_id, db_session)
        uj.status = new_status
        db_session.commit()
        return jsonify({"ok": True, "status": new_status})
    finally:
        db_session.close()


@app.route("/api/jobs/manual", methods=["POST"])
@login_required
def api_add_manual_job():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    text = (data.get("text") or "").strip()
    if not url and not text:
        return jsonify({"error": "paste a posting URL and/or description text"}), 400

    title = (data.get("title") or "").strip()
    company = (data.get("company") or "").strip()
    location = (data.get("location") or "").strip()
    hr_email = extract_email(text) if text else ""

    if not title and text:
        first_line = next((l.strip() for l in text.splitlines() if l.strip()), "")
        title = first_line[:120]
    if not title:
        title = "Manual Entry"
    title = re.sub(EMAIL_RE_PATTERN, " ", title)
    title = re.split(r"\s+(?:Email|Contact|Apply|For more|For details|Location|Salary)\b", title, maxsplit=1)[0]
    title = title.strip(" .,;:-")
    if not title:
        title = "Manual Entry"

    source_site = urlparse(url).netloc.lower() if url else "manual"
    raw = {
        "title": title,
        "company": company,
        "location": location,
        "source_site": source_site,
        "posting_url": url,
        "snippet": text[:280],
        "role": data.get("role") or "",
        "hr_email": hr_email,
        "posted_date": datetime.utcnow(),
    }
    job_dict = _clean_job(raw)
    job_dict["hr_email"] = hr_email
    if not job_dict["role"]:
        job_dict["role"] = "manual"

    db_session = SessionLocal()
    try:
        existing = db_session.query(Job).filter_by(
            source_site=job_dict["source_site"], posting_url=job_dict["posting_url"]
        ).first()
        if existing:
            return jsonify({"error": "job already exists", "id": existing.id}), 409

        row = Job(
            title=job_dict["title"],
            company=job_dict["company"],
            location=job_dict["location"],
            source_site=job_dict["source_site"],
            posting_url=job_dict["posting_url"],
            snippet=job_dict["snippet"],
            role=job_dict["role"],
            relevance_score=job_dict["relevance_score"],
            status="new",
            posted_date=job_dict["posted_date"],
            created_at=datetime.utcnow(),
        )
        db_session.add(row)
        db_session.flush()
        uj = get_user_job(session["user_id"], row.id, db_session)
        uj.status = "new"
        db_session.commit()
        return jsonify({"ok": True, "id": row.id})
    finally:
        db_session.close()


@app.route("/api/profile", methods=["GET"])
@login_required
def api_get_profile():
    db_session = SessionLocal()
    try:
        profile = get_or_create_profile(session["user_id"], db_session)
        return jsonify(profile_to_dict(profile))
    finally:
        db_session.close()


@app.route("/api/profile", methods=["POST"])
@login_required
def api_save_profile():
    data = request.get_json(silent=True) or {}
    db_session = SessionLocal()
    try:
        profile = get_or_create_profile(session["user_id"], db_session)
        for key in ("name", "email", "phone", "linkedin", "github", "portfolio",
                    "summary", "education", "experience"):
            if key in data:
                setattr(profile, key, str(data[key] or "").strip())
        if "skills" in data and isinstance(data["skills"], list):
            profile.skills = ", ".join(str(s).strip() for s in data["skills"] if str(s).strip())
        db_session.commit()
        return jsonify({"ok": True, "profile": profile_to_dict(profile)})
    finally:
        db_session.close()


def start_web(host="127.0.0.1", port=5001):
    print(f"  [web] JobPilot dashboard at http://localhost:{port}")
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    start_web()
