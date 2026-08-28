import re
import threading
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal, Job, init_db
from app.sources import fetch_bangladesh_jobs
from app.filter import detect_role, score_job, is_relevant, detect_experience_level
from app.gmail_link import build_job_gmail_link
from app.cv.parse import extract_email
from app.config import load_search_config

try:
    from app.scrapers.fb_post_search import fetch_fb_posts
except Exception:
    fetch_fb_posts = None  # type: ignore

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
        "experience_level": "",
        "hr_email": raw.get("hr_email") or extract_email(snippet),
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
        except Exception as e:
            import traceback
            print(f"[scan] ERROR: {e}")
            traceback.print_exc()
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

    # Facebook Post Search (opt-in, disabled by default)
    if fetch_fb_posts is not None:
        try:
            from app.db import is_fb_post_search_enabled
            if is_fb_post_search_enabled():
                fb_jobs = fetch_fb_posts(verbose=verbose)
                if fb_jobs:
                    if verbose:
                        print(f"  [fb_post_search] collected {len(fb_jobs)} jobs")
                    raw_jobs.extend(fb_jobs)
            else:
                if verbose:
                    print("  [fb_post_search] disabled — skipping")
        except Exception as e:
            if verbose:
                print(f"  [fb_post_search] fetch failed: {e}")

    cutoff = datetime.utcnow() - timedelta(days=max_age_days)

    session = SessionLocal()

    # Cleanup: delete stale FB posts older than max_age_days
    try:
        from app.config import load_fb_post_search_config
        fb_cfg = load_fb_post_search_config()
        fb_max_age = int(fb_cfg.get("max_age_days", 3))
        fb_cutoff = datetime.utcnow() - timedelta(days=fb_max_age)
        deleted = session.query(Job).filter(
            func.lower(Job.source_site) == "facebook_post_search",
            func.coalesce(Job.posted_date, Job.created_at) < fb_cutoff,
        ).delete(synchronize_session="fetch")
        if deleted and verbose:
            print(f"  [fb_post_search] cleaned up {deleted} stale posts (older than {fb_max_age} days)")
        session.flush()
    except Exception as e:
        if verbose:
            print(f"  [fb_post_search] cleanup failed: {e}")

    p_dict = {"skills": []}

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
            job["experience_level"] = detect_experience_level(job)
            if not is_relevant(job, min_score):
                no_role += 1
                continue
            if job["posted_date"] and job["posted_date"] < cutoff:
                too_old += 1
                continue
            job["gmail_link"] = build_job_gmail_link(
                {"title": job["title"], "company": job["company"],
                 "location": job["location"], "hr_email": job["hr_email"]},
                p_dict,
            )

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
                experience_level=job["experience_level"],
                hr_email=job["hr_email"],
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
