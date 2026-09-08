from __future__ import annotations
import os
import re
import json
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, jsonify, request, session, redirect, url_for, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, and_, or_

from app.db import SessionLocal, Job, Profile, User, UserJob, UserCV, TailorSession, get_user_job, get_user_cvs, profile_to_dict, get_or_create_profile
from app.pipeline import run_scan_async
from app.gmail_link import (
    build_job_gmail_link, build_subject, build_body, build_gmail_link,
    _infer_job_from_text,
)
from app.cv.parse import extract_email
from app.paths import CONFIG_DIR
from app.config import load_search_config
from app.filter import skill_gap_analysis, company_links
from app.learning_topics import TOPICS
from app.sources import get_bdjobs_jobfairs

DAYS_OPTIONS = [("1", "1 day"), ("3", "3 days"), ("7", "1 week"), ("30", "1 month")]
EXPERIENCE_OPTIONS = [
    ("fresher", "Fresher (0-1 yr)"),
    ("2y", "2 years"),
    ("3y", "3 years"),
    ("3y_plus", "3+ years"),
]

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "jobpilot-super-secret-key-change-in-prod")


def _startup_scan():
    """Trigger an initial job scan + periodic rescan every 6 hours."""
    import threading

    def _scan():
        from app.db import init_db
        init_db()
        run_scan_async()

    def _periodic():
        while True:
            threading.Event().wait(6 * 3600)
            try:
                run_scan_async()
            except Exception:
                pass

    threading.Thread(target=_scan, daemon=True).start()
    threading.Thread(target=_periodic, daemon=True).start()


try:
    _startup_scan()
except Exception:
    pass

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


def _user_relevance_score(profile_skills: list, job) -> float:
    """Score job relevance based on user profile skills vs job title+snippet."""
    if not profile_skills:
        return job.relevance_score or 0.0
    title = (job.title or "").lower()
    snippet = (job.snippet or "").lower()
    text = f"{title} {snippet}"
    hits = 0
    for skill in profile_skills:
        if skill.lower() in text:
            hits += 1
    if hits == 0:
        return 0.0
    ratio = hits / max(len(profile_skills), 1)
    return round(min(0.5 + ratio * 0.5, 1.0), 2)


_EARLY_RE = re.compile(r"(Be an early applicant\s*[·•\-–]?\s*[^\n<]+)", re.IGNORECASE)


def _extract_early_applicant(job) -> tuple[str, str]:
    """Extract 'Be an early applicant ...' text from title/snippet.
    Returns (cleaned_text, early_applicant_text).
    """
    title = job.title or ""
    snippet = job.snippet or ""
    combined = f"{title} {snippet}"
    m = _EARLY_RE.search(combined)
    if not m:
        return snippet, ""
    early = m.group(1).strip()
    cleaned_snippet = snippet.replace(early, "").strip()
    cleaned_title = title.replace(early, "").strip()
    return cleaned_snippet, early


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
                return redirect(url_for("dashboard"))
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
            return redirect(url_for("dashboard"))
        finally:
            db_session.close()
    return render_template("register.html", require_invite=require_invite)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    db_session = SessionLocal()
    try:
        stats = {
            "jobs": db_session.query(func.count(Job.id)).scalar() or 0,
            "roles": db_session.query(func.count(func.distinct(Job.role))).scalar() or 0,
            "sources": db_session.query(func.count(func.distinct(Job.source_site))).scalar() or 0,
            "users": db_session.query(func.count(User.id)).scalar() or 0,
        }
    finally:
        db_session.close()
    return render_template("home.html", stats=stats)


@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session["user_id"]
    db_session = SessionLocal()
    try:
        user = db_session.query(User).get(user_id)
        onboarding_done = bool(user and user.onboarding_done)
    finally:
        db_session.close()

    status = request.args.get("status", "").strip()
    days = request.args.get("days", "")
    page = request.args.get("page", "1")
    role_filter = request.args.get("role", "").strip().lower()
    exp_filter = request.args.get("exp", "").strip()
    sort = (request.args.get("sort", "newonly") or "newonly").strip().lower()
    if sort not in ("newonly", "applied", "deadline", "all"):
        sort = "newonly"

    # Use user preferences as defaults if no filter specified
    if not days and onboarding_done:
        days = str(user.pref_days) if user and user.pref_days else "30"
    if not days:
        days = "30"
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
        q = db_session.query(Job).filter(func.lower(Job.source_site) != "remote_jobs")
        if role_filter:
            q = q.filter(Job.role == role_filter)
        if exp_filter and exp_filter in ("fresher", "2y", "3y", "3y_plus"):
            q = q.filter(Job.experience_level == exp_filter)
        q = q.filter((Job.posted_date.is_(None)) | (Job.posted_date >= cutoff))

        if status in ("applied", "dismissed"):
            q = q.join(UserJob, and_(UserJob.job_id == Job.id, UserJob.user_id == user_id, UserJob.status == status))
        elif status == "new":
            q = q.outerjoin(UserJob, and_(UserJob.job_id == Job.id, UserJob.user_id == user_id))
            q = q.filter(or_(UserJob.status == "new", UserJob.status.is_(None)))
        elif sort == "applied":
            q = q.join(UserJob, and_(UserJob.job_id == Job.id, UserJob.user_id == user_id, UserJob.status == "applied"))
        elif sort == "newonly":
            q = q.outerjoin(UserJob, and_(UserJob.job_id == Job.id, UserJob.user_id == user_id))
            q = q.filter(or_(UserJob.status == "new", UserJob.status.is_(None)))

        total = q.count()
        PER_PAGE = 5
        total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
        if page > total_pages:
            page = total_pages
        offset = (page - 1) * PER_PAGE

        # Fetch all jobs for this filter, compute per-job fields, then sort in Python
        all_jobs = q.order_by(Job.posted_date.desc()).all()

        profile = get_or_create_profile(user_id, db_session)
        p_dict = profile_to_dict(profile)

        for job in all_jobs:
            uj = get_user_job(user_id, job.id, db_session)
            job.status = uj.status

            # HR email: use the stored one from DB
            hr_email = job.hr_email or ""

            # Build Gmail link — auto-generate for relevance=1, or if hr_email found
            if _is_useful_email(hr_email):
                job.gmail_link = build_job_gmail_link(
                    {"title": job.title, "company": job.company,
                     "location": job.location, "hr_email": hr_email},
                    p_dict,
                )
            else:
                job.gmail_link = ""

            # Per-user relevance score
            job.user_relevance = _user_relevance_score(p_dict.get("skills", []), job)
            job.exp_label = {"fresher": "Fresher", "2y": "2 yr", "3y": "3 yr", "3y_plus": "3+ yr"}.get(job.experience_level, "")

            # Extract early-applicant badge text from title/snippet
            cleaned_snippet, early_text = _extract_early_applicant(job)
            job.snippet = cleaned_snippet
            job.early_applicant = early_text

            # Skill gap analysis
            job.skill_gap = skill_gap_analysis(p_dict.get("skills", []), job.title, job.snippet or "")

            # Deadline urgency
            job.deadline_urgency = None
            if job.deadline:
                days_left = (job.deadline - datetime.utcnow()).days
                if days_left <= 3:
                    job.deadline_urgency = max(0, days_left)

            # Follow-up reminder (applied > 5 days ago, no follow-up yet)
            job.follow_up_needed = False
            if job.status == "applied" and uj.follow_up_at is None:
                if uj.updated_at and (datetime.utcnow() - uj.updated_at).days >= 5:
                    job.follow_up_needed = True

            # Company research links
            job.company_links = company_links(job.company)

        # Apply Python-side sort
        _EPOCH = datetime.min
        if sort == "deadline":
            all_jobs.sort(key=lambda j: (j.deadline or datetime.max, j.posted_date or _EPOCH))
        else:
            all_jobs.sort(key=lambda j: j.posted_date or _EPOCH, reverse=True)

        jobs = all_jobs[offset:offset + PER_PAGE]

        search_cfg = load_search_config()
        all_roles = search_cfg.get("roles", []) + search_cfg.get("custom_roles", [])
        return render_template(
            "index.html",
            jobs=jobs,
            active_status=status,
            active_days=str(days),
            active_role=role_filter,
            active_exp=exp_filter,
            active_sort=sort,
            active_page=page,
            total_pages=total_pages,
            days_options=DAYS_OPTIONS,
            experience_options=EXPERIENCE_OPTIONS,
            roles=search_cfg.get("roles", []),
            custom_roles=search_cfg.get("custom_roles", []),
            all_roles=all_roles,
            now=datetime.utcnow(),
            counts=_status_counts(db_session, user_id, cutoff, role_filter, exp_filter),
            username=session.get("username"),
            onboarding_done=onboarding_done,
            has_skills=bool(p_dict.get("skills")),
            bdjobs_jobfairs=get_bdjobs_jobfairs(),
        )
    finally:
        db_session.close()


def _status_counts(db_session, user_id, cutoff, role_filter="", exp_filter="") -> dict:
    base_q = db_session.query(Job).filter(func.lower(Job.source_site) != "remote_jobs", (Job.posted_date.is_(None)) | (Job.posted_date >= cutoff))
    if role_filter:
        base_q = base_q.filter(Job.role == role_filter)
    if exp_filter and exp_filter in ("fresher", "2y", "3y", "3y_plus"):
        base_q = base_q.filter(Job.experience_level == exp_filter)
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


@app.route("/api/cron/scan", methods=["POST"])
def api_cron_scan():
    """Unauthenticated endpoint for GitHub Actions / cron to trigger scans."""
    secret = request.headers.get("X-Cron-Secret") or request.args.get("secret")
    expected = os.getenv("CRON_SECRET", "")
    if expected and secret != expected:
        return jsonify({"error": "unauthorized"}), 401
    from app.db import init_db
    init_db()
    started = run_scan_async()
    db_session = SessionLocal()
    try:
        job_count = db_session.query(Job).count()
    finally:
        db_session.close()
    return jsonify({"ok": True, "started": started, "jobs_in_db": job_count})


@app.route("/api/debug")
def api_debug():
    """Public debug endpoint — shows DB status and job count."""
    from app.db import init_db, IS_POSTGRES
    from app.paths import DATABASE_URL
    try:
        init_db()
        db_session = SessionLocal()
        try:
            job_count = db_session.query(Job).count()
            from sqlalchemy import text
            db_url_masked = DATABASE_URL[:30] + "..." if len(DATABASE_URL) > 30 else DATABASE_URL
            return jsonify({
                "ok": True,
                "db_type": "postgres" if IS_POSTGRES else "sqlite",
                "database_url_prefix": db_url_masked,
                "jobs_in_db": job_count,
                "scan_running": scan_is_running(),
            })
        finally:
            db_session.close()
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "db_type": "postgres" if IS_POSTGRES else "sqlite"})


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
        if new_status == "applied":
            uj.follow_up_at = datetime.utcnow() + timedelta(days=5)
        elif new_status == "new":
            uj.follow_up_at = None
        db_session.commit()
        return jsonify({"ok": True, "status": new_status})
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


@app.route("/api/profile/parse-cv", methods=["POST"])
@login_required
def api_parse_cv():
    """Accept a CV file (PDF/DOCX), extract text, parse into profile fields."""
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "no file"}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".pdf", ".docx", ".doc"):
        return jsonify({"error": "unsupported file type; use PDF or DOCX"}), 400
    import tempfile
    from app.cv.parse import extract_text
    from app.cv.profile import profile_from_text

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    try:
        file.save(tmp.name)
        tmp.close()
        text = extract_text(tmp.name)
        if not text.strip():
            return jsonify({"error": "could not extract text from CV"}), 400
        parsed = profile_from_text(text)
        return jsonify({"ok": True, "profile": parsed})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


@app.route("/api/gmail/from-text", methods=["POST"])
@login_required
def api_gmail_from_text():
    """Paste a job posting; extract the HR email and build a Gmail compose link."""
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "paste a job posting first"}), 400

    db_session = SessionLocal()
    try:
        profile = get_or_create_profile(session["user_id"], db_session)
        p_dict = profile_to_dict(profile)
    finally:
        db_session.close()

    hr_email = extract_email(text)
    if not hr_email:
        return jsonify({
            "ok": False, "found": False,
            "message": "No email address found in the pasted text.",
        })

    job = _infer_job_from_text(text, hr_email)
    job["hr_email"] = hr_email
    subject = build_subject(job)
    body = build_body(job, p_dict)
    link = build_gmail_link(hr_email, subject, body)
    return jsonify({
        "ok": True, "found": True,
        "to": hr_email, "subject": subject, "body": body, "gmail_link": link,
    })


def start_web(host="0.0.0.0", port=None):
    port = port or int(os.environ.get("PORT", 5001))
    print(f"  [web] JobPilot dashboard at http://localhost:{port}")
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


@app.route("/api/onboarding", methods=["POST"])
@login_required
def api_onboarding():
    data = request.get_json(silent=True) or {}
    roles = data.get("roles") or []
    days = int(data.get("days") or 30)
    if days not in (1, 3, 7, 30):
        days = 30
    db_session = SessionLocal()
    try:
        user = db_session.query(User).get(session["user_id"])
        if user:
            user.onboarding_done = 1
            user.pref_roles = ",".join(str(r).strip() for r in roles if r)
            user.pref_days = days
            db_session.commit()
        return jsonify({"ok": True})
    finally:
        db_session.close()


@app.route("/learning")
@login_required
def learning():
    # Rotate topics: show one topic at a time, changes every 20 minutes
    now = datetime.utcnow()
    minutes = (now.hour * 60 + now.minute)
    topic_index = (minutes // 20) % len(TOPICS)
    topic = TOPICS[topic_index]
    return render_template("learning.html", topic=topic, all_topics=TOPICS, username=session.get("username"))


@app.route("/applications")
@login_required
def applications():
    """Applications page — shows all jobs (regular + remote) the user has interacted with."""
    user_id = session["user_id"]
    status_filter = request.args.get("status", "all").strip()
    source_filter = request.args.get("source", "all").strip()

    db_session = SessionLocal()
    try:
        q = db_session.query(Job).join(UserJob, UserJob.job_id == Job.id).filter(UserJob.user_id == user_id)

        if status_filter in ("applied", "dismissed", "new"):
            q = q.filter(UserJob.status == status_filter)

        if source_filter == "remote":
            q = q.filter(func.lower(Job.source_site) == "remote_jobs")
        elif source_filter == "regular":
            q = q.filter(func.lower(Job.source_site) != "remote_jobs")

        jobs = q.order_by(Job.posted_date.desc()).all()

        # Attach user job status
        user_jobs_map = {}
        ujs = db_session.query(UserJob).filter(UserJob.user_id == user_id).all()
        for uj in ujs:
            user_jobs_map[uj.job_id] = uj.status

        for job in jobs:
            job.user_status = user_jobs_map.get(job.id, "new")

        # Counts
        all_uj = db_session.query(UserJob).filter(UserJob.user_id == user_id).all()
        applied_count = sum(1 for u in all_uj if u.status == "applied")
        dismissed_count = sum(1 for u in all_uj if u.status == "dismissed")

        return render_template(
            "applications.html",
            jobs=jobs,
            applied_count=applied_count,
            dismissed_count=dismissed_count,
            active_status=status_filter,
            active_source=source_filter,
            username=session.get("username"),
        )
    finally:
        db_session.close()


REMOTE_DAYS_OPTIONS = [
    ("0", "Any time"),
    ("7", "Last 1 week"),
    ("14", "Last 2 weeks"),
    ("30", "Last 1 month"),
    ("60", "Last 2 months"),
]


@app.route("/remote_jobs")
@login_required
def remote_jobs():
    """Remote jobs page — international positions from top platforms."""
    user_id = session["user_id"]

    days = request.args.get("days", "0")
    try:
        days_int = int(days)
    except ValueError:
        days_int = 0
    if days_int not in (0, 7, 14, 30, 60):
        days_int = 0
    cutoff = datetime.utcnow() - timedelta(days=days_int) if days_int else None

    role_filter = request.args.get("role", "").strip()
    exp_filter = request.args.get("experience", "").strip()
    company_filter = request.args.get("company", "").strip()

    db_session = SessionLocal()
    try:
        q = db_session.query(Job).filter(func.lower(Job.source_site) == "remote_jobs")
        if cutoff is not None:
            q = q.filter(Job.posted_date >= cutoff)

        total = q.count()
        jobs = q.order_by(Job.posted_date.desc()).limit(100).all()

        profile = get_or_create_profile(user_id, db_session)
        p_dict = profile_to_dict(profile)

        companies = set()
        all_roles = set()
        all_exps = set()
        for job in jobs:
            job.user_relevance = _user_relevance_score(p_dict.get("skills", []), job)
            cleaned_snippet, early_text = _extract_early_applicant(job)
            job.snippet = cleaned_snippet
            job.early_applicant = early_text
            companies.add(job.company or "")
            # Extract role tags and experience from snippet/title
            from app.scrapers.remote_jobs import _extract_role_tags, _extract_experience_level
            full_text = f"{job.title or ''} {cleaned_snippet}"
            role_tags = _extract_role_tags(job.title or "", cleaned_snippet)
            exp_level = _extract_experience_level(job.title or "", cleaned_snippet)
            job.role_tags_json = ",".join(role_tags)
            job.experience_level = exp_level
            all_roles.update(role_tags)
            all_exps.add(exp_level)

        return render_template(
            "remote_jobs.html",
            jobs=jobs,
            total=total,
            active_days=str(days_int),
            remote_days_options=REMOTE_DAYS_OPTIONS,
            companies=sorted(companies - {""}),
            all_roles=sorted(all_roles),
            all_exps=sorted(all_exps),
            active_role=role_filter,
            active_exp=exp_filter,
            active_company=company_filter,
            username=session.get("username"),
        )
    finally:
        db_session.close()


@app.route("/api/remote_jobs/scan", methods=["POST"])
@login_required
def api_remote_scan():
    """Trigger a remote jobs scan."""
    from app.pipeline import run_scan_async
    started = run_scan_async()
    if not started:
        return jsonify({"ok": True, "started": False, "error": "scan already running"}), 202
    return jsonify({"ok": True, "started": True})


# ============================================================
# Tailor CV feature
# ============================================================

def _normalize_profile_to_editor(p_dict: dict) -> dict:
    """Convert flat profile dict (from profile_to_dict) to nested editor format."""
    pi = {
        "full_name": p_dict.get("name", "") or "",
        "job_title": "",
        "email": p_dict.get("email", "") or "",
        "phone": p_dict.get("phone", "") or "",
        "location": "",
        "website": {"text": "", "url": ""},
        "linkedin": {"text": "LinkedIn", "url": p_dict.get("linkedin", "") or ""},
        "github": {"text": "GitHub", "url": p_dict.get("github", "") or ""},
        "portfolio": {"text": "Portfolio", "url": p_dict.get("portfolio", "") or ""},
        "other_links": [],
    }

    summary = p_dict.get("summary", "") or ""
    skills = p_dict.get("skills", []) or []
    skill_groups = [{"category": "", "items": skills}] if skills else []

    experience = []
    exp_text = p_dict.get("experience", "") or ""
    if exp_text.strip():
        blocks = [b.strip() for b in exp_text.split("\n\n") if b.strip()]
        if not blocks:
            blocks = [exp_text.strip()]
        for block in blocks:
            lines = block.split("\n")
            title = lines[0] if lines else ""
            bullets = [l.strip() for l in lines[1:] if l.strip()] if len(lines) > 1 else [block]
            experience.append({
                "company": "",
                "title": title,
                "location": "",
                "start_date": "",
                "end_date": "",
                "bullets": bullets,
            })

    education = []
    edu_text = p_dict.get("education", "") or ""
    if edu_text.strip():
        blocks = [b.strip() for b in edu_text.split("\n\n") if b.strip()]
        if not blocks:
            blocks = [edu_text.strip()]
        for block in blocks:
            lines = block.split("\n")
            degree = lines[0] if lines else ""
            details = "\n".join(lines[1:]) if len(lines) > 1 else block
            education.append({
                "degree": degree,
                "institution": "",
                "start_date": "",
                "end_date": "",
                "details": details,
            })

    return {
        "personal_info": pi,
        "summary": summary,
        "skills": skills,
        "skill_groups": skill_groups,
        "experience": experience,
        "education": education,
        "projects": [],
        "certifications": [],
        "extracurricular": [],
        "languages": [],
        "references": [],
        "custom_sections": [],
        "links": [],
    }


def _find_best_cv(job_text: str, user_cvs: list) -> "UserCV | None":
    """Find the best matching CV for a job based on skill overlap."""
    if not user_cvs:
        return None

    job_lower = job_text.lower()
    job_words = set(re.findall(r"\b[a-z]{2,}\b", job_lower))

    best_cv = None
    best_score = -1

    for cv in user_cvs:
        parsed = {}
        if cv.parsed_profile:
            try:
                parsed = json.loads(cv.parsed_profile)
            except Exception:
                pass
        skills = parsed.get("skills", [])
        if not skills:
            continue

        cv_words = set()
        for skill in skills:
            cv_words.update(re.findall(r"\b[a-z]{2,}\b", skill.lower()))

        overlap = len(job_words & cv_words)
        score = overlap / max(len(job_words), 1)

        if score > best_score:
            best_score = score
            best_cv = cv

    # Fallback: if no CV had skills, return the most recent one
    if best_cv is None and user_cvs:
        best_cv = user_cvs[0]

    return best_cv


def _structured_content_from_profile(parsed: dict, canonical: Optional[dict] = None) -> dict:
    """Convert a parsed profile dict to the editor format, using canonical if available."""
    if canonical and isinstance(canonical, dict) and canonical.get("personal_info"):
        return canonical
    return _normalize_profile_to_editor(parsed)


def _style_to_css(style: dict) -> dict:
    """Convert a style config dict to pre-computed CSS values for the template."""
    font_family = style.get("font_family", "Inter")
    font_scale = float(style.get("font_scale", 1))
    spacing_scale = float(style.get("spacing_scale", 1))
    accent = style.get("accent_color", "#1a365d")
    page_size = style.get("page_size", "a4")

    return {
        "css_font": f"'{font_family}', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        "css_accent": accent,
        "css_page_w": "215.9mm" if page_size == "letter" else "210mm",
        "css_page_h": "279.4mm" if page_size == "letter" else "297mm",
        "css_font_body": f"{10.5 * font_scale}pt",
        "css_font_name": f"{20 * font_scale}pt",
        "css_font_section": f"{11 * font_scale}pt",
        "css_font_small": f"{9.5 * font_scale}pt",
        "css_font_date": f"{9 * font_scale}pt",
        "css_gap_section": f"{12 * spacing_scale}px",
        "css_gap_entry": f"{8 * spacing_scale}px",
    }


@app.route("/tailor/<int:job_id>")
@login_required
def tailor_cv(job_id):
    """Tailor CV page for a specific job."""
    db_session = SessionLocal()
    try:
        job = db_session.query(Job).get(job_id)
        if not job:
            return "Job not found", 404
        
        ts = db_session.query(TailorSession).filter_by(
            user_id=session["user_id"], job_id=job_id
        ).first()
        
        profile = get_or_create_profile(session["user_id"], db_session)
        p_dict = profile_to_dict(profile)
        
        cv_content = {}
        jd_text = ""
        suggestions = []
        if ts:
            if ts.cv_content:
                cv_content = json.loads(ts.cv_content)
            jd_text = ts.jd_text or ""
            if ts.suggestions:
                suggestions = json.loads(ts.suggestions)
        
        if not cv_content:
            cv_content = _normalize_profile_to_editor(p_dict)
        
        return render_template(
            "tailor.html",
            job=job,
            cv_content=cv_content,
            jd_text=jd_text,
            suggestions=suggestions,
            username=session.get("username"),
        )
    finally:
        db_session.close()


@app.route("/api/tailor/<int:job_id>/upload-cv", methods=["POST"])
@login_required
def api_tailor_upload_cv(job_id):
    """Upload and parse a CV file for tailoring."""
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "no file"}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".pdf", ".docx", ".doc"):
        return jsonify({"error": "unsupported file type; use PDF or DOCX"}), 400

    from app.paths import UPLOAD_DIR
    import uuid

    # Save file permanently to uploads directory
    file_id = str(uuid.uuid4())[:8]
    saved_name = f"tailor_{session['user_id']}_{job_id}_{file_id}{ext}"
    saved_path = os.path.join(UPLOAD_DIR, saved_name)
    file.save(saved_path)

    from app.cv.parse import extract_text
    from app.cv.profile import profile_from_text

    text = extract_text(saved_path)
    if not text.strip():
        return jsonify({"error": "could not extract text from CV"}), 400
    parsed = profile_from_text(text)
    normalized = _normalize_profile_to_editor(parsed)

    db_session = SessionLocal()
    try:
        # Create a UserCV record so this CV is reusable across jobs
        cv_name = os.path.splitext(file.filename)[0]
        user_cv = UserCV(
            user_id=session["user_id"],
            name=cv_name,
            file_path=saved_name,
            parsed_profile=json.dumps(parsed),
            canonical_profile=json.dumps(normalized),
        )
        db_session.add(user_cv)
        db_session.flush()

        # Create/update the tailor session
        ts = db_session.query(TailorSession).filter_by(
            user_id=session["user_id"], job_id=job_id
        ).first()
        if not ts:
            ts = TailorSession(user_id=session["user_id"], job_id=job_id)
            db_session.add(ts)
        ts.cv_file = saved_name
        ts.cv_content = json.dumps(normalized)
        ts.base_cv_id = user_cv.id
        ts.updated_at = datetime.utcnow()
        db_session.commit()

        return jsonify({"ok": True, "profile": normalized, "cv_id": user_cv.id})
    finally:
        db_session.close()


@app.route("/api/tailor/<int:job_id>/save-content", methods=["POST"])
@login_required
def api_tailor_save_content(job_id):
    """Save edited CV content and style config."""
    data = request.get_json(silent=True) or {}
    cv_content = data.get("cv_content", {})
    style_config = data.get("style", {})
    
    db_session = SessionLocal()
    try:
        ts = db_session.query(TailorSession).filter_by(
            user_id=session["user_id"], job_id=job_id
        ).first()
        if not ts:
            ts = TailorSession(user_id=session["user_id"], job_id=job_id)
            db_session.add(ts)
        import json
        ts.cv_content = json.dumps(cv_content)
        if style_config:
            ts.style_config = json.dumps(style_config)
        ts.updated_at = datetime.utcnow()
        db_session.commit()
        return jsonify({"ok": True})
    finally:
        db_session.close()


@app.route("/api/tailor/<int:job_id>/compare", methods=["POST"])
@login_required
def api_tailor_compare(job_id):
    """Compare CV with job description and generate suggestions."""
    data = request.get_json(silent=True) or {}
    jd_text = data.get("jd_text", "").strip()
    
    if not jd_text:
        return jsonify({"error": "job description is required"}), 400
    
    db_session = SessionLocal()
    try:
        job = db_session.query(Job).get(job_id)
        if not job:
            return jsonify({"error": "job not found"}), 404
        
        # Get or create tailor session
        ts = db_session.query(TailorSession).filter_by(
            user_id=session["user_id"], job_id=job_id
        ).first()
        
        import json
        
        # Get CV content from session or fall back to user profile
        if ts and ts.cv_content:
            cv_content = json.loads(ts.cv_content)
        else:
            profile = get_or_create_profile(session["user_id"], db_session)
            cv_content = profile_to_dict(profile)
        
        # Generate suggestions using Gemini
        from app.gemini import generate_json, gemini_available
        
        # Create a comprehensive prompt for comparison
        COMPARE_PROMPT = """Compare the candidate's CV with the job description and identify specific improvements.
        
Job Description:
{jd_text}

Job Title: {job_title}
Company: {company}

Candidate's Current CV:
{cv_json}

Analyze and return a JSON array of specific, actionable suggestions. Each suggestion should have:
- "section": the CV section to modify (summary, skills, experience, education)
- "current": the current text in that section
- "suggested": the improved text
- "reason": why this change helps match the job

Focus on:
1. Adding missing keywords from JD to summary/skills
2. Rephrasing experience bullets to match JD language
3. Highlighting relevant skills
4. Not fabricating experience

Return ONLY valid JSON array. Max 8 suggestions.""".format(
            jd_text=jd_text[:2000],
            job_title=job.title or "",
            company=job.company or "",
            cv_json=json.dumps(cv_content)
        )
        
        suggestions = []
        if gemini_available():
            try:
                result = generate_json(COMPARE_PROMPT, temperature=0.3)
                if isinstance(result, list):
                    suggestions = result
            except Exception as e:
                print(f"[tailor] Gemini comparison failed: {e}")
        
        # Fallback: simple keyword-based suggestions
        if not suggestions:
            suggestions = _generate_fallback_suggestions(cv_content, jd_text, job)
        
        # Save or update session
        if not ts:
            ts = TailorSession(user_id=session["user_id"], job_id=job_id)
            db_session.add(ts)
        ts.jd_text = jd_text
        ts.suggestions = json.dumps(suggestions)
        ts.updated_at = datetime.utcnow()
        db_session.commit()
        
        return jsonify({"ok": True, "suggestions": suggestions})
    finally:
        db_session.close()


def _generate_fallback_suggestions(cv_content, jd_text, job):
    """Generate basic suggestions without Gemini."""
    suggestions = []
    jd_lower = jd_text.lower()
    
    # Check summary
    summary = cv_content.get("summary", "")
    if summary:
        # Find keywords in JD not in summary
        jd_keywords = set()
        for word in ["python", "java", "javascript", "react", "node", "sql", "aws", "docker", "kubernetes", "git", "api", "rest", "graphql", "microservices", "agile", "scrum", "ci/cd", "testing", "jenkins", "github", "gitlab", "jira", "confluence", "linux", "bash", "html", "css", "typescript", "angular", "vue", "django", "flask", "fastapi", "spring", "postgresql", "mysql", "mongodb", "redis", "elasticsearch"]:
            if word in jd_lower and word not in summary.lower():
                jd_keywords.add(word)
        if jd_keywords:
            suggestions.append({
                "section": "summary",
                "current": summary[:200],
                "suggested": summary + " " + ", ".join(list(jd_keywords)[:5]),
                "reason": f"Add relevant keywords from job description: {', '.join(list(jd_keywords)[:5])}"
            })
    
    # Check skills
    skills = cv_content.get("skills", [])
    if isinstance(skills, list):
        skill_text = ", ".join(skills).lower()
        missing_skills = []
        for word in ["python", "java", "javascript", "react", "node", "sql", "aws", "docker", "kubernetes", "git", "api", "rest", "graphql", "microservices", "agile", "scrum", "ci/cd", "testing", "jenkins", "github", "gitlab", "jira", "confluence", "linux", "bash", "html", "css", "typescript", "angular", "vue", "django", "flask", "fastapi", "spring", "postgresql", "mysql", "mongodb", "redis", "elasticsearch"]:
            if word in jd_lower and word not in skill_text:
                missing_skills.append(word)
        if missing_skills:
            suggestions.append({
                "section": "skills",
                "current": ", ".join(skills[:10]),
                "suggested": ", ".join(skills + missing_skills[:5]),
                "reason": f"Add missing skills from job description: {', '.join(missing_skills[:5])}"
            })
    
    return suggestions[:8]


@app.route("/api/tailor/<int:job_id>/apply-suggestion", methods=["POST"])
@login_required
def api_tailor_apply_suggestion(job_id):
    """Apply a suggestion to the CV content."""
    data = request.get_json(silent=True) or {}
    suggestion = data.get("suggestion", {})
    
    db_session = SessionLocal()
    try:
        ts = db_session.query(TailorSession).filter_by(
            user_id=session["user_id"], job_id=job_id
        ).first()
        if not ts:
            return jsonify({"error": "session not found"}), 404
        
        import json
        cv_content = json.loads(ts.cv_content) if ts.cv_content else {}
        
        section = suggestion.get("section")
        suggested = suggestion.get("suggested", "")
        
        if section == "summary":
            cv_content["summary"] = suggested
        elif section == "skills":
            # Parse suggested skills
            if isinstance(suggested, str):
                cv_content["skills"] = [s.strip() for s in suggested.split(",") if s.strip()]
            elif isinstance(suggested, list):
                cv_content["skills"] = suggested
        elif section == "experience":
            cv_content["experience"] = suggested
        elif section == "education":
            cv_content["education"] = suggested
        
        ts.cv_content = json.dumps(cv_content)
        ts.updated_at = datetime.utcnow()
        db_session.commit()
        
        return jsonify({"ok": True, "cv_content": cv_content})
    finally:
        db_session.close()


@app.route("/api/tailor/<int:job_id>/session", methods=["GET"])
@login_required
def api_tailor_session(job_id):
    """Get current tailor session data as JSON."""
    db_session = SessionLocal()
    try:
        ts = db_session.query(TailorSession).filter_by(
            user_id=session["user_id"], job_id=job_id
        ).first()
        
        import json
        cv_content = {}
        style_config = {}
        jd_text = ""
        suggestions = []
        cv_file = ""
        base_cv_id = None
        
        if ts:
            if ts.cv_content:
                cv_content = json.loads(ts.cv_content)
            if ts.style_config:
                style_config = json.loads(ts.style_config)
            jd_text = ts.jd_text or ""
            if ts.suggestions:
                suggestions = json.loads(ts.suggestions)
            cv_file = ts.cv_file or ""
            base_cv_id = ts.base_cv_id
        
        return jsonify({
            "ok": True,
            "cv_content": cv_content,
            "style": style_config,
            "jd_text": jd_text,
            "suggestions": suggestions,
            "cv_file": cv_file,
            "cv_id": base_cv_id,
        })
    finally:
        db_session.close()


@app.route("/api/tailor/<int:job_id>/cvs", methods=["GET"])
@login_required
def api_tailor_list_cvs(job_id):
    """List all uploaded CVs for the current user with match scores."""

    db_session = SessionLocal()
    try:
        job = db_session.query(Job).get(job_id)
        if not job:
            return jsonify({"error": "job not found"}), 404

        user_cvs = get_user_cvs(session["user_id"], db_session)

        # Find best matching CV
        job_text = f"{job.title or ''} {job.company or ''} {job.snippet or ''} {job.role or ''} {job.location or ''}"
        best_cv = _find_best_cv(job_text, user_cvs)

        cv_list = []
        for cv in user_cvs:
            parsed = {}
            if cv.parsed_profile:
                try:
                    parsed = json.loads(cv.parsed_profile)
                except Exception:
                    pass
            cv_list.append({
                "id": cv.id,
                "name": cv.name,
                "is_best_match": cv.id == best_cv.id if best_cv else False,
                "skills": parsed.get("skills", []),
            })

        return jsonify({"ok": True, "cvs": cv_list, "best_match_id": best_cv.id if best_cv else None})
    finally:
        db_session.close()


@app.route("/api/tailor/<int:job_id>/select-cv", methods=["POST"])
@login_required
def api_tailor_select_cv(job_id):
    """Switch the base CV for a tailor session and re-seed content."""
    data = request.get_json(silent=True) or {}
    cv_id = data.get("cv_id")
    user_id = session["user_id"]

    db_session = SessionLocal()
    try:
        if not cv_id:
            return jsonify({"error": "cv_id required"}), 400

        # Verify CV belongs to user
        cv = db_session.query(UserCV).filter_by(id=cv_id, user_id=user_id).first()
        if not cv:
            return jsonify({"error": "CV not found"}), 404

        # Get or create tailor session
        ts = db_session.query(TailorSession).filter_by(user_id=user_id, job_id=job_id).first()
        if not ts:
            ts = TailorSession(user_id=user_id, job_id=job_id)
            db_session.add(ts)
            db_session.flush()

        # Set base CV and re-seed content from parsed profile
        ts.base_cv_id = cv_id

        # Parse the CV file to get structured content
        parsed = {}
        if cv.parsed_profile:
            try:
                parsed = json.loads(cv.parsed_profile)
            except Exception:
                pass
        canonical = None
        if cv.canonical_profile:
            try:
                canonical = json.loads(cv.canonical_profile)
            except Exception:
                pass
        ts.cv_content = json.dumps(_structured_content_from_profile(parsed, canonical))

        # Copy CV file path for download
        if cv.file_path:
            ts.cv_file = cv.file_path

        db_session.commit()

        return jsonify({
            "ok": True,
            "cv_id": cv_id,
            "cv_name": cv.name,
            "cv_content": json.loads(ts.cv_content),
        })
    finally:
        db_session.close()


@app.route("/api/tailor/<int:job_id>/preview", methods=["GET"])
@login_required
def api_tailor_preview(job_id):
    """Generate a preview HTML of the tailored CV."""
    db_session = SessionLocal()
    try:
        job = db_session.query(Job).get(job_id)
        if not job:
            return jsonify({"error": "job not found"}), 404
        
        profile = get_or_create_profile(session["user_id"], db_session)
        p_dict = profile_to_dict(profile)
        
        ts = db_session.query(TailorSession).filter_by(
            user_id=session["user_id"], job_id=job_id
        ).first()
        
        import json
        if ts and ts.cv_content:
            cv_content = json.loads(ts.cv_content)
        else:
            cv_content = _normalize_profile_to_editor(p_dict)

        style_config = {}
        if ts and ts.style_config:
            try:
                style_config = json.loads(ts.style_config)
            except Exception:
                pass

        css = _style_to_css(style_config)
        return render_template(
            "cv_preview.html",
            cv_content=cv_content,
            style=style_config,
            **css,
        )
    finally:
        db_session.close()


@app.route("/api/tailor/<int:job_id>/download", methods=["GET"])
@login_required
def api_tailor_download(job_id):
    """Download the tailored CV as DOCX or PDF.

    PDF is rendered from the exact same cv_preview.html template used by the
    live preview — guaranteeing visual parity via WeasyPrint.
    """
    format_type = request.args.get("format", "pdf")
    
    db_session = SessionLocal()
    try:
        job = db_session.query(Job).get(job_id)
        if not job:
            return jsonify({"error": "job not found"}), 404
        
        profile = get_or_create_profile(session["user_id"], db_session)
        p_dict = profile_to_dict(profile)
        
        ts = db_session.query(TailorSession).filter_by(
            user_id=session["user_id"], job_id=job_id
        ).first()
        
        import json
        if ts and ts.cv_content:
            cv_content = json.loads(ts.cv_content)
        else:
            cv_content = _normalize_profile_to_editor(p_dict)

        style_config = {}
        if ts and ts.style_config:
            try:
                style_config = json.loads(ts.style_config)
            except Exception:
                pass
        
        if format_type == "docx":
            from app.cv.ats import generate_ats_cv
            ats = generate_ats_cv({
                "title": job.title,
                "company": job.company,
                "snippet": job.snippet,
            }, cv_content)
            template_path = None
            if ts and ts.cv_file:
                from app.paths import UPLOAD_DIR
                full_path = os.path.join(UPLOAD_DIR, ts.cv_file)
                if os.path.exists(full_path):
                    template_path = full_path
            from app.cv.render import render_cv_docx
            docx_path = render_cv_docx(job_id, cv_content, ats, template_path=template_path)
            return send_file(docx_path, mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document", as_attachment=True, download_name=f"Tailored_CV_{job.title.replace(' ', '_')}.docx")

        # PDF: render the same cv_preview.html template, convert via xhtml2pdf
        css = _style_to_css(style_config)
        html_str = render_template("cv_preview.html", cv_content=cv_content, style=style_config, **css)
        from xhtml2pdf import pisa
        import tempfile
        pdf_output = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        pisa.CreatePDF(html_str, dest=pdf_output)
        pdf_output.close()
        return send_file(pdf_output.name, mimetype="application/pdf", as_attachment=True,
                         download_name=f"Tailored_CV_{job.title.replace(' ', '_')}.pdf")
    finally:
        db_session.close()


@app.route("/cv-preview-static")
def cv_preview_static():
    """Standalone test page showing the CV template with sample data. No auth required."""
    return render_template("cv_static.html")


@app.route("/api/cv-preview-static/render")
def api_cv_preview_static_render():
    """Render the CV template with sample data. No auth required. Used by the static test page iframe."""
    from app.cv.schema import SAMPLE_CV
    css = _style_to_css({})
    return render_template("cv_preview.html", cv_content=SAMPLE_CV, style={}, **css)


@app.route("/api/cv/render", methods=["POST"])
def api_cv_render():
    """Render the CV template from JSON and return the full HTML document.

    Accepts POST with JSON body:
        { "cv_content": {...}, "style": {...} }

    Returns: rendered HTML string (the full cv_preview.html document).
    Used by the tailor page for live preview via srcdoc.
    """
    data = request.get_json(silent=True) or {}
    cv_content = data.get("cv_content", {})
    style = data.get("style", {})
    css = _style_to_css(style)
    return render_template("cv_preview.html", cv_content=cv_content, style=style, **css)


if __name__ == "__main__":
    start_web()
