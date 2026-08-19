import os
import re
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, and_, or_

from app.db import SessionLocal, Job, Profile, User, UserJob, get_user_job, profile_to_dict, get_or_create_profile
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
    sort = (request.args.get("sort", "latest") or "latest").strip().lower()
    if sort not in ("latest", "deadline"):
        sort = "latest"

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
        q = db_session.query(Job)
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
    base_q = db_session.query(Job).filter((Job.posted_date.is_(None)) | (Job.posted_date >= cutoff))
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


if __name__ == "__main__":
    start_web()
