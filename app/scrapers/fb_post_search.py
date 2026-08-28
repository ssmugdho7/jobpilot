"""
Facebook Post Search — Serper.dev text search for recent FB job posts.

Uses Serper POST /search with tbs=qdr:d (past day) to fetch only recent
Facebook posts about hiring. No image download, no Gemini vision — just
text search results filtered by domain, role keywords, and location.

Flow:
  1. Serper search: q = "site:facebook.com <query>", tbs=qdr:d, gl=bd
  2. Domain filter: only facebook.com results pass
  3. Keyword filter: title+snippet must contain role signal AND location
  4. Build job record with posted_date = now() (recent from tbs)
  5. Dedup by posting_url

Cost: ~600 queries/month (10 queries x 2 scans/day) — well within free tier.
"""

import os
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import requests

from app.config import load_fb_post_search_config
from app.db import is_fb_post_search_enabled

SERPER_ENDPOINT = "https://google.serper.dev/search"


def _normalize_host(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
        return host.lower().strip()
    except Exception:
        return ""


def is_allowed_domain(url: str, allowed: list[str] | None = None) -> bool:
    """Return True iff url's host is on the allowlist (suffix match)."""
    if allowed is None:
        cfg = load_fb_post_search_config()
        allowed = cfg.get("allowed_domains") or []
    host = _normalize_host(url)
    if not host or not allowed:
        return False
    for entry in allowed:
        e = entry.strip().lower().lstrip("*.")
        if not e:
            continue
        if host == e or host.endswith("." + e):
            return True
    return False


def _title_passes_filter(
    title: str,
    snippet: str = "",
    title_keywords: list[str] | None = None,
    location_keywords: list[str] | None = None,
) -> bool:
    """Return True iff title+snippet contains a role keyword AND a location keyword."""
    cfg = load_fb_post_search_config()
    if title_keywords is None:
        title_keywords = cfg.get("title_filter_keywords") or []
    if location_keywords is None:
        location_keywords = cfg.get("location_keywords") or ["dhaka", "bangladesh"]

    text = f"{title or ''} {snippet or ''}".lower()
    has_role = any(kw.lower() in text for kw in title_keywords)
    has_location = any(kw.lower() in text for kw in location_keywords)
    return has_role and has_location


def _serper_search(query: str, api_key: str, num: int = 10, tbs: str = "qdr:d", timeout: int = 15) -> list[dict[str, Any]]:
    """POST to Serper /search with tbs time filter."""
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    q_with_site = f"site:facebook.com {query}"
    body: dict[str, Any] = {"q": q_with_site, "gl": "bd", "num": max(1, min(10, num))}
    if tbs:
        body["tbs"] = tbs
    resp = requests.post(SERPER_ENDPOINT, headers=headers, json=body, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data.get("organic") or []


def get_enabled() -> bool:
    """Check if FB post search is enabled."""
    return is_fb_post_search_enabled()


def fetch_fb_posts(max_queries: int | None = None, verbose: bool = True) -> list[dict[str, Any]]:
    """
    Run the Serper post search pipeline for Facebook job posts.

    Returns job dicts with:
        title, company, location, source_site="facebook_post_search",
        posting_url, snippet, posted_date=now(), deadline=None

    Serper tbs=qdr:d ensures only recent results. posted_date is set to
    now() since we know the result is recent but don't have exact dates.
    When disabled, returns [] without network calls.
    """
    if not get_enabled():
        if verbose:
            print("  [fb_post_search] skipped (disabled — toggle on in /fb_posts)")
        return []

    cfg = load_fb_post_search_config()
    api_key = (cfg.get("serper_api_key") or os.getenv("SERPER_API_KEY", "") or "").strip()
    if not api_key:
        if verbose:
            print("  [fb_post_search] skipped (missing SERPER_API_KEY)")
        return []

    queries: list[str] = cfg.get("queries") or []
    if not queries:
        if verbose:
            print("  [fb_post_search] no queries configured")
        return []

    allowed_domains: list[str] = cfg.get("allowed_domains") or []
    max_q = max_queries if max_queries is not None else int(cfg.get("max_queries_per_run", 5))
    per_query = int(cfg.get("results_per_query", 10))
    delay_q = float(cfg.get("delay_between_queries", 1.5))
    timeout = int(cfg.get("request_timeout", 15))
    tbs = cfg.get("tbs", "qdr:d")

    if verbose:
        print(f"  [fb_post_search] tbs={tbs!r}")

    selected_queries = queries[:max_q]
    now = datetime.utcnow()

    summary = {
        "queries_run": 0,
        "posts_found": 0,
        "excluded_by_domain": 0,
        "excluded_by_keyword": 0,
        "deduped": 0,
        "inserted": 0,
    }

    seen_links: set[str] = set()
    results: list[dict[str, Any]] = []

    for qi, query in enumerate(selected_queries):
        if verbose:
            print(f"  [fb_post_search] query {qi+1}/{len(selected_queries)}: {query!r}")
        try:
            items = _serper_search(query, api_key, num=per_query, tbs=tbs, timeout=timeout)
        except Exception as e:
            if verbose:
                print(f"    -> Serper error: {e}")
            summary["queries_run"] += 1
            if delay_q and qi < len(selected_queries) - 1:
                time.sleep(delay_q)
            continue

        summary["queries_run"] += 1
        summary["posts_found"] += len(items)

        for item in items:
            link = item.get("link") or ""
            title = item.get("title") or ""
            snippet = item.get("snippet") or item.get("description") or ""

            if not link:
                continue

            if not is_allowed_domain(link, allowed_domains):
                summary["excluded_by_domain"] += 1
                continue

            if not _title_passes_filter(title, snippet):
                summary["excluded_by_keyword"] += 1
                continue

            if link in seen_links:
                summary["deduped"] += 1
                continue
            seen_links.add(link)

            title_clean = title.strip() or "Facebook Job"
            low_combined = f"{title} {snippet}".lower()
            location = "Dhaka, Bangladesh" if "dhaka" in low_combined else "Bangladesh"

            job = {
                "title": title_clean[:200],
                "company": "Facebook",
                "location": location,
                "source_site": "facebook_post_search",
                "posting_url": link,
                "snippet": (snippet or title_clean)[:1000],
                "posted_date": now,
                "deadline": None,
            }
            results.append(job)
            summary["inserted"] += 1
            if verbose:
                print(f"    -> kept: {title_clean[:60]!r}")

        if delay_q and qi < len(selected_queries) - 1:
            time.sleep(delay_q)

    if verbose:
        print(
            f"  [fb_post_search] summary: queries={summary['queries_run']} "
            f"posts={summary['posts_found']} excluded_domain={summary['excluded_by_domain']} "
            f"excluded_keyword={summary['excluded_by_keyword']} deduped={summary['deduped']} "
            f"inserted={summary['inserted']}"
        )

    return results
