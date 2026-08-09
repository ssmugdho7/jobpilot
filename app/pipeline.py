import re
import threading
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal, Job, Profile, init_db, profile_to_dict, get_or_create_profile
from app.sources import fetch_bangladesh_jobs
from app.filter import detect_role, score_job, is_relevant
from app.gmail_link import build_job_gmail_link
from app.config import load_search_config

_scan_lock = threading.Lock()
_scan_running = False

NOISE_TITLES = ["self employed", "freelancer", "looking for job", "job seeker"]


def _is_noise(title: str) -> bool:
    low = (title or "").lower()
    return any(n in low for n in NOISE_TITLES)


def _clean_job(raw: dict) -> dict:
    title = (raw.get("title") or "").strip()
    company = (raw.get("company") or "").strip()
    posting_url = raw.get("posting_url") or raw.get("url") or ""
    snippet = re.sub(r"\s+", " ", (raw.get("snippet") or "").strip())[:1000]
    if not company:
        m = re.search(r"\bat\s+(.+)$", title)
        if m:
            company = m.group(1).strip().rstrip("()")
            title = title[: m.start()].strip().rstrip("-–—: ")

    posted_date = raw.get("posted_date") or None
    if not posted_date:
        posted_date = datetime.utcnow()

    return {
        "title": title or posting_url or "Untitled",
        "company": company,
        "location": raw.get("location") or "",
        "source_site": raw.get("source_site") or "",
        "posting_url": posting_url,
        "snippet": snippet,
        "role": raw.get("role") or raw.get("_role") or detect_role(raw),
        "relevance_score": 0.0,
        "posted_date": posted_date,
        "deadline": raw.get("deadline") or None,
    }


def scan_is_running() -> bool:
    return _scan_running


def run_scan_async() -> bool:
    """Start a scan in a background thread if none is running. Returns True if started."""
    global _scan_running
    with _scan_lock:
        if _scan_running:
            return False
        _scan_running = True

    def _worker():
        global _scan_running
        try:
            run_scan()
        finally:
            with _scan_lock:
                _scan_running = False

    threading.Thread(target=_worker, daemon=True).start()
    return True


def run_scan(verbose: bool = True) -> int:
    init_db()
    cfg = load_search_config()
    min_score = cfg.get("min_relevance_score", 0.0)
    max_age_days = int(cfg.get("max_age_days", 30))

    if verbose:
        print("=== JobPilot scan (Bangladesh) ===")

    raw_jobs = []
    try:
        raw_jobs = fetch_bangladesh_jobs(max_age_days)
        if verbose:
            print(f"  [sources] collected {len(raw_jobs)} raw jobs")
    except Exception as e:
        if verbose:
            print(f"  [sources] fetch failed: {e}")

    cutoff = datetime.utcnow() - timedelta(days=max_age_days)

    session = SessionLocal()
    profile = get_or_create_profile(session)
    p_dict = profile_to_dict(profile)

    inserted = 0
    seen = 0
    no_role = 0
    too_old = 0
    run_seen: set[tuple] = set()
    try:
        for raw in raw_jobs:
            job = _clean_job(raw)
            if not job["role"] or _is_noise(job["title"]):
                no_role += 1
                continue
            job["relevance_score"] = score_job(job)
            if not is_relevant(job, min_score):
                no_role += 1
                continue
            if job["posted_date"] and job["posted_date"] < cutoff:
                too_old += 1
                continue
            job["gmail_link"] = build_job_gmail_link(job, p_dict)

            dup_key = (job["source_site"], job["posting_url"])
            if dup_key in run_seen:
                seen += 1
                continue
            run_seen.add(dup_key)

            existing = session.query(Job).filter_by(
                source_site=job["source_site"], posting_url=job["posting_url"]
            ).first()
            if existing:
                seen += 1
                continue

            row = Job(
                title=job["title"],
                company=job["company"],
                location=job["location"],
                source_site=job["source_site"],
                posting_url=job["posting_url"],
                snippet=job["snippet"],
                role=job["role"],
                relevance_score=job["relevance_score"],
                gmail_link=job["gmail_link"],
                posted_date=job["posted_date"],
                deadline=job["deadline"],
                created_at=datetime.utcnow(),
            )
            session.add(row)
            session.flush()
            inserted += 1
        session.commit()
    except IntegrityError:
        session.rollback()
    finally:
        session.close()

    if verbose:
        print(f"  [scan] inserted={inserted} skipped_dups={seen} no_role={no_role} too_old={too_old}")
    return inserted


def list_jobs():
    init_db()
    session = SessionLocal()
    try:
        return session.query(Job).order_by(Job.posted_date.desc()).all()
    finally:
        session.close()
