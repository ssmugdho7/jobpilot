"""
Facebook Graph API scraper for job posts.

Uses the Graph API to fetch posts from specific Facebook pages/groups
that post CSE-related jobs in Bangladesh.

Flow:
  1. Fetch posts from configured pages/groups
  2. Filter posts by job keywords and location
  3. Return job dicts with posting_url, title, snippet, etc.

Token: Use a Page Access Token or User Access Token with pages_read_engagement.
"""

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from app.config import load_fb_post_search_config
from app.db import is_fb_post_search_enabled

GRAPH_API_VERSION = "v19.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


def _get_access_token() -> str:
    """Get access token from config or env."""
    cfg = load_fb_post_search_config()
    token = cfg.get("access_token") or os.getenv("FACEBOOK_ACCESS_TOKEN", "")
    return (token or "").strip()


def _get_page_posts(page_id: str, token: str, page_type: str = "page", limit: int = 25, since: datetime | None = None) -> list[dict]:
    """Get recent posts from a Facebook page or group."""
    # For groups, we need to use /group_id/feed instead of /page_id/posts
    if page_type == "group":
        url = f"{GRAPH_API_BASE}/{page_id}/feed"
    else:
        url = f"{GRAPH_API_BASE}/{page_id}/posts"

    params = {
        "access_token": token,
        "limit": limit,
        "fields": "id,message,created_time,link,from",
    }
    if since:
        params["since"] = int(since.timestamp())

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])
    except Exception as e:
        print(f"    [fb_graph] posts fetch error for {page_id}: {e}")
        return []


def _is_job_post(message: str, job_keywords: list[str]) -> bool:
    """Check if a post message is about a job."""
    if not message:
        return False
    text = message.lower()
    return any(kw.lower() in text for kw in job_keywords)


def _has_bd_location(message: str, location_keywords: list[str]) -> bool:
    """Check if a post mentions Bangladesh or BD locations."""
    if not message:
        return False
    text = message.lower()
    return any(loc.lower() in text for loc in location_keywords)


def _extract_title(message: str) -> str:
    """Extract a title from the post message."""
    if not message:
        return "Facebook Job Post"
    # Take first line or first 100 chars
    first_line = message.split("\n")[0].strip()
    if len(first_line) > 100:
        first_line = first_line[:97] + "..."
    return first_line or "Facebook Job Post"


def _extract_location(message: str, location_keywords: list[str]) -> str:
    """Extract location from the post message."""
    if not message:
        return "Bangladesh"
    text = message.lower()
    for loc in ["dhaka", "chittagong", "chattogram", "sylhet", "rajshahi", "khulna"]:
        if loc in text:
            return loc.title() + ", Bangladesh"
    if "bangladesh" in text or "bd" in text:
        return "Bangladesh"
    return "Bangladesh"


def get_enabled() -> bool:
    """Check if FB post search is enabled."""
    return is_fb_post_search_enabled()


def fetch_fb_posts(verbose: bool = True) -> list[dict[str, Any]]:
    """
    Fetch job posts from configured Facebook pages/groups.

    Returns job dicts with:
        title, company, location, source_site="facebook_graph_api",
        posting_url, snippet, posted_date, deadline=None

    When disabled or no token, returns [] without network calls.
    """
    if not get_enabled():
        if verbose:
            print("  [fb_graph] skipped (disabled — toggle on in /fb_posts)")
        return []

    token = _get_access_token()
    if not token:
        if verbose:
            print("  [fb_graph] skipped (missing FACEBOOK_ACCESS_TOKEN)")
        return []

    cfg = load_fb_post_search_config()
    pages = cfg.get("pages") or []
    if not pages:
        if verbose:
            print("  [fb_graph] no pages configured")
        return []

    job_keywords = cfg.get("job_keywords") or [
        "hiring", "vacancy", "job", "career", "apply", "opening",
        "we are hiring", "join our team", "position", "recruitment",
        "software engineer", "developer", "web developer", "data analyst",
        "devops", "frontend", "backend", "full stack", "mobile developer",
        "ai engineer", "ml engineer", "qa engineer", "it executive",
    ]
    location_keywords = cfg.get("location_keywords") or [
        "dhaka", "chittagong", "chattogram", "sylhet", "rajshahi", "khulna",
        "bangladesh", "bd",
    ]
    max_age_days = int(cfg.get("max_age_days", 3))
    posts_per_page = int(cfg.get("posts_per_page", 25))
    since = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    if verbose:
        print(f"  [fb_graph] fetching from {len(pages)} pages/groups, max {max_age_days} days old")

    seen_post_ids: set[str] = set()
    results: list[dict[str, Any]] = []

    for page in pages:
        page_id = page.get("id", "")
        page_name = page.get("name", "Unknown")
        page_type = page.get("type", "page")

        if not page_id:
            continue

        if verbose:
            print(f"    -> {page_name} ({page_id}, {page_type})")

        posts = _get_page_posts(page_id, token, page_type, limit=posts_per_page, since=since)

        for post in posts:
            post_id = post.get("id", "")
            message = post.get("message", "")
            created_time = post.get("created_time", "")
            link = post.get("link", "")

            if not post_id or post_id in seen_post_ids:
                continue

            if not _is_job_post(message, job_keywords):
                continue

            if not _has_bd_location(message, location_keywords):
                continue

            # Build posting URL
            if link:
                posting_url = link
            elif post_id:
                # For groups, the URL format is different
                if page_type == "group":
                    posting_url = f"https://www.facebook.com/groups/{page_id}/posts/{post_id}"
                else:
                    posting_url = f"https://www.facebook.com/{page_id}/posts/{post_id}"
            else:
                continue

            seen_post_ids.add(post_id)

            # Parse created_time
            posted_date = datetime.now(timezone.utc)
            if created_time:
                try:
                    posted_date = datetime.fromisoformat(created_time.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            title = _extract_title(message)
            location = _extract_location(message, location_keywords)

            job = {
                "title": title[:200],
                "company": page_name,
                "location": location,
                "source_site": "facebook_graph_api",
                "posting_url": posting_url,
                "snippet": (message or title)[:1000],
                "posted_date": posted_date.replace(tzinfo=None),
                "deadline": None,
            }
            results.append(job)

            if verbose:
                print(f"      -> kept: {title[:60]!r}")

    if verbose:
        print(f"  [fb_graph] summary: {len(results)} job posts found")

    return results
