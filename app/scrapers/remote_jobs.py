"""Remote Jobs scraper — fetches tech/CSE jobs from international remote platforms.

Companies scraped:
- SuperAnnotate, Mercor, Toptal, Arc.dev, Turing, Remotebase
- Outlier AI, OpenTrain AI, Invisible Technologies, Quantigo AI
- CrowdGen, TELUS International AI, OneForma, Toloka AI
- Welocalize, Clickworker

Logic:
- Scrapes career pages for remote tech/CSE jobs
- Adds "🇧🇩 Bangladesh" badge if job is specifically for Bangladesh/Dhaka
- Skips onsite/area-specific jobs not for Bangladesh
"""

import re
import time
from datetime import datetime, timedelta
from typing import Optional

import requests
from bs4 import BeautifulSoup

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

# Tech/CSE keywords for filtering
TECH_KEYWORDS = [
    "software", "engineer", "developer", "programmer", "coder",
    "frontend", "backend", "fullstack", "full stack", "full-stack",
    "web developer", "mobile developer", "ios developer", "android developer",
    "python", "javascript", "typescript", "react", "node", "django", "flask",
    "fastapi", "spring", "rails", "golang", "rust", "java", "kotlin", "swift",
    "devops", "sre", "site reliability", "cloud", "aws", "azure", "gcp",
    "data scientist", "data engineer", "machine learning", "ml engineer",
    "ai engineer", "deep learning", "nlp", "computer vision",
    "database", "sql", "postgres", "mongodb", "redis",
    "api", "backend", "microservices", "kubernetes", "docker",
    "qa", "quality assurance", "test engineer", "automation engineer",
    "cybersecurity", "security engineer", "penetration tester",
    "product manager", "technical program manager",
    "ux designer", "ui developer", "graphic designer",
    "it support", "systems administrator", "network engineer",
    "blockchain", "web3", "solidity",
    "flutter", "react native", "ionic",
    "php", "laravel", "wordpress", "shopify",
    "c++", "c#", ".net", "scala", "elixir",
    "data analyst", "business intelligence", "bi developer",
    "scrum master", "agile",
    "cto", "vp engineering", "tech lead", "architect",
]

# Bangladesh-related location keywords
BD_KEYWORDS = [
    "bangladesh", "bd", "dhaka", "chittagong", "chattogram", "sylhet",
    "rajshahi", "khulna", "barishal", "barisal", "rangpur", "mymensingh",
]

def _headers() -> dict:
    import random
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }


def _is_tech_job(title: str, snippet: str = "") -> bool:
    """Check if a job is tech/CSE related."""
    text = f"{title} {snippet}".lower()
    return any(kw in text for kw in TECH_KEYWORDS)


def _is_bangladesh_location(location: str, snippet: str = "") -> bool:
    """Check if job is specifically for Bangladesh."""
    text = f"{location} {snippet}".lower()
    return any(kw in text for kw in BD_KEYWORDS)


def _clean_text(text: str) -> str:
    """Clean and truncate text."""
    return re.sub(r"\s+", " ", text).strip()[:500]


# ---------------------------------------------------------------------------
# Role tags and experience level extraction
# ---------------------------------------------------------------------------

# Role category tags
ROLE_TAGS = {
    "frontend": ["frontend", "front-end", "front end", "react", "vue", "angular", "ui developer", "css", "html", "javascript"],
    "backend": ["backend", "back-end", "back end", "api", "server", "django", "flask", "fastapi", "spring", "rails", "node.js", "node"],
    "fullstack": ["fullstack", "full-stack", "full stack"],
    "mobile": ["mobile", "ios", "android", "flutter", "react native", "swift", "kotlin"],
    "data_science": ["data scientist", "data science", "machine learning", "ml engineer", "deep learning", "nlp", "computer vision", "ai engineer", "artificial intelligence"],
    "data_engineering": ["data engineer", "data engineering", "etl", "data pipeline", "spark", "airflow"],
    "devops": ["devops", "sre", "site reliability", "cloud engineer", "infrastructure", "kubernetes", "docker", "aws", "azure", "gcp"],
    "qa": ["qa", "quality assurance", "test engineer", "automation engineer", "sdet", "testing"],
    "security": ["security", "cybersecurity", "penetration tester", "infosec", "application security"],
    "design": ["designer", "ux", "ui", "figma", "graphic designer", "product designer"],
    "product": ["product manager", "technical program manager", "scrum master", "project manager"],
    "blockchain": ["blockchain", "web3", "solidity", "crypto"],
    "general": ["software engineer", "software developer", "programmer", "coder", "it support", "systems administrator", "network engineer"],
}

# Experience level patterns
EXPERIENCE_PATTERNS = {
    "entry": [
        r"\bentry[\s-]?level\b", r"\bjunior\b", r"\b0[\s-]?2\s*(?:years?|yrs?)\b",
        r"\bfresher\b", r"\bbeginner\b", r"\bintern\b", r"\btrainee\b",
        r"\bgraduate\b", r"\bnew grad\b",
    ],
    "mid": [
        r"\bmid[\s-]?level\b", r"\bintermediate\b", r"\b2[\s-]?5\s*(?:years?|yrs?)\b",
        r"\b3[\s-]?5\s*(?:years?|yrs?)\b", r"\b2[\s-]?4\s*(?:years?|yrs?)\b",
    ],
    "senior": [
        r"\bsenior\b", r"\bsr\b", r"\blead\b", r"\bprincipal\b", r"\bstaff\b",
        r"\b5\+?\s*(?:years?|yrs?)\b", r"\b5[\s-]?10\s*(?:years?|yrs?)\b",
        r"\bexpert\b", r"\barchitect\b",
    ],
    "lead": [
        r"\btech lead\b", r"\bteam lead\b", r"\bengineering manager\b",
        r"\bcto\b", r"\bvp\b", r"\bdirector\b", r"\bhead of\b",
    ],
}


def _extract_role_tags(title: str, snippet: str = "") -> list[str]:
    """Extract role category tags from job text."""
    text = f"{title} {snippet}".lower()
    tags = []
    for tag, keywords in ROLE_TAGS.items():
        if any(kw in text for kw in keywords):
            tags.append(tag)
    return tags if tags else ["general"]


def _extract_experience_level(title: str, snippet: str = "") -> str:
    """Extract experience level from job text."""
    text = f"{title} {snippet}".lower()
    for level, patterns in EXPERIENCE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text):
                return level
    # Default heuristic: if title contains senior/lead/ principal, assume senior
    if any(w in text for w in ["senior", "sr.", "lead", "principal", "staff", "architect"]):
        return "senior"
    if any(w in text for w in ["junior", "jr.", "entry", "intern", "trainee", "fresher"]):
        return "entry"
    return "mid"


# ---------------------------------------------------------------------------
# Company scrapers
# ---------------------------------------------------------------------------

def _scrape_greenhouse(board_token: str, company_name: str) -> list[dict]:
    """Scrape Greenhouse job board API."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
    try:
        resp = requests.get(url, timeout=15, headers=_headers())
        if resp.status_code != 200:
            return []
        data = resp.json()
        jobs = []
        for job in data.get("jobs", []):
            title = job.get("title", "")
            location = job.get("location", {}).get("name", "")
            url = job.get("absolute_url", "")
            snippet = _clean_text(job.get("description", "")[:300])
            if not _is_tech_job(title, snippet):
                continue
            is_bd = _is_bangladesh_location(location, snippet)
            posted = job.get("updated_at") or job.get("posted_at")
            posted_date = None
            if posted:
                try:
                    posted_date = datetime.fromisoformat(posted.replace("Z", "+00:00")).replace(tzinfo=None)
                except Exception:
                    pass
            jobs.append({
                "title": title,
                "company": company_name,
                "location": location,
                "source_site": "remote_jobs",
                "posting_url": url,
                "snippet": snippet,
                "posted_date": posted_date or datetime.utcnow(),
                "_is_bd_remote": is_bd,
                "role_tags": _extract_role_tags(title, snippet),
                "experience_level": _extract_experience_level(title, snippet),
            })
        return jobs
    except Exception as e:
        print(f"  [remote_jobs] greenhouse {company_name}: {e}")
        return []


def _scrape_lever(slug: str, company_name: str) -> list[dict]:
    """Scrape Lever job postings API."""
    url = f"https://api.lever.co/v0/postings/{slug}"
    try:
        resp = requests.get(url, params={"mode": "json"}, timeout=15, headers=_headers())
        if resp.status_code != 200:
            return []
        data = resp.json()
        jobs = []
        for job in data:
            title = job.get("text", "")
            team = job.get("categories", {}).get("team", "")
            department = job.get("categories", {}).get("department", "")
            location = job.get("categories", {}).get("location", "")
            url = job.get("hostedUrl", "")
            snippet = _clean_text(job.get("descriptionPlain", "")[:300])
            full_text = f"{title} {team} {department} {snippet}"
            if not _is_tech_job(title, full_text):
                continue
            is_bd = _is_bangladesh_location(location, snippet)
            posted = job.get("createdAt")
            posted_date = None
            if posted:
                try:
                    posted_date = datetime.fromtimestamp(posted / 1000)
                except Exception:
                    pass
            jobs.append({
                "title": title,
                "company": company_name,
                "location": location,
                "source_site": "remote_jobs",
                "posting_url": url,
                "snippet": snippet,
                "posted_date": posted_date or datetime.utcnow(),
                "_is_bd_remote": is_bd,
                "role_tags": _extract_role_tags(title, full_text),
                "experience_level": _extract_experience_level(title, full_text),
            })
        return jobs
    except Exception as e:
        print(f"  [remote_jobs] lever {company_name}: {e}")
        return []


def _scrape_ashby(slug: str, company_name: str) -> list[dict]:
    """Scrape Ashby job board API."""
    url = f"https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams"
    try:
        payload = {
            "operationName": "ApiJobBoardWithTeams",
            "variables": {"organizationHostedJobsPageName": slug},
            "query": "query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) { jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) { teams { name jobs { id title locationName employmentType descriptionHtml descriptionPlain createdAt updatedAt } } } }"
        }
        resp = requests.post(url, json=payload, timeout=15, headers={**_headers(), "Content-Type": "application/json"})
        if resp.status_code != 200:
            return []
        data = resp.json().get("data", {}).get("jobBoard", {})
        jobs = []
        for team in data.get("teams", []):
            for job in team.get("jobs", []):
                title = job.get("title", "")
                location = job.get("locationName", "")
                url = f"https://jobs.ashbyhq.com/{slug}/{job.get('id', '')}"
                snippet = _clean_text(BeautifulSoup(job.get("descriptionHtml", ""), "html.parser").get_text()[:300])
                if not _is_tech_job(title, snippet):
                    continue
                is_bd = _is_bangladesh_location(location, snippet)
                posted = job.get("createdAt")
                posted_date = None
                if posted:
                    try:
                        posted_date = datetime.fromisoformat(posted.replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        pass
                jobs.append({
                    "title": title,
                    "company": company_name,
                    "location": location,
                    "source_site": "remote_jobs",
                    "posting_url": url,
                    "snippet": snippet,
                    "posted_date": posted_date or datetime.utcnow(),
                    "_is_bd_remote": is_bd,
                    "role_tags": _extract_role_tags(title, snippet),
                    "experience_level": _extract_experience_level(title, snippet),
                })
        return jobs
    except Exception as e:
        print(f"  [remote_jobs] ashby {company_name}: {e}")
        return []


def _scrape_html_careers(url: str, company_name: str) -> list[dict]:
    """Scrape a static HTML career page for job links."""
    try:
        resp = requests.get(url, timeout=15, headers=_headers())
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        jobs = []
        # Look for job listing patterns
        for link in soup.find_all("a", href=True):
            text = link.get_text(strip=True)
            href = link["href"]
            if not text or len(text) < 5:
                continue
            # Skip non-job links
            if any(skip in text.lower() for skip in ["login", "sign up", "about", "contact", "privacy", "terms"]):
                continue
            # Check if it looks like a job title
            if _is_tech_job(text):
                if not href.startswith("http"):
                    from urllib.parse import urljoin
                    href = urljoin(url, href)
                # Try to get location from parent/sibling elements
                location = ""
                parent = link.find_parent(["div", "li", "tr", "article"])
                if parent:
                    loc_elem = parent.find(class_=re.compile(r"location|loc", re.I))
                    if loc_elem:
                        location = loc_elem.get_text(strip=True)
                snippet = _clean_text(parent.get_text()[:300]) if parent else text
                is_bd = _is_bangladesh_location(location, snippet)
                jobs.append({
                    "title": text[:150],
                    "company": company_name,
                    "location": location,
                    "source_site": "remote_jobs",
                    "posting_url": href,
                    "snippet": snippet,
                    "posted_date": datetime.utcnow(),
                    "_is_bd_remote": is_bd,
                    "role_tags": _extract_role_tags(text, snippet),
                    "experience_level": _extract_experience_level(text, snippet),
                })
        return jobs[:20]  # Limit to 20 per company
    except Exception as e:
        print(f"  [remote_jobs] html {company_name}: {e}")
        return []


def _scrape_smartrecruiters(company_slug: str, company_name: str) -> list[dict]:
    """Scrape SmartRecruiters API."""
    url = f"https://api.smartrecruiters.com/v1/companies/{company_slug}/postings"
    try:
        resp = requests.get(url, params={"limit": 100, "offset": 0}, timeout=15, headers=_headers())
        if resp.status_code != 200:
            return []
        data = resp.json().get("content", [])
        jobs = []
        for job in data:
            title = job.get("name", "")
            location = job.get("location", {}).get("city", "") + ", " + job.get("location", {}).get("country", "")
            url = job.get("ref", "")
            snippet = _clean_text(job.get("JobPosting", {}).get("description", "")[:300])
            if not _is_tech_job(title, snippet):
                continue
            is_bd = _is_bangladesh_location(location, snippet)
            posted = job.get("releasedDate")
            posted_date = None
            if posted:
                try:
                    posted_date = datetime.fromtimestamp(posted / 1000)
                except Exception:
                    pass
            jobs.append({
                "title": title,
                "company": company_name,
                "location": location,
                "source_site": "remote_jobs",
                "posting_url": url,
                "snippet": snippet,
                "posted_date": posted_date or datetime.utcnow(),
                "_is_bd_remote": is_bd,
                "role_tags": _extract_role_tags(title, snippet),
                "experience_level": _extract_experience_level(title, snippet),
            })
        return jobs
    except Exception as e:
        print(f"  [remote_jobs] smartrecruiters {company_name}: {e}")
        return []


# ---------------------------------------------------------------------------
# Main scraper
# ---------------------------------------------------------------------------

# Remote job platforms configuration
REMOTE_PLATFORMS = [
    # Companies with proper career pages
    {
        "name": "Mercor",
        "type": "greenhouse",
        "board": "mercor",
    },
    {
        "name": "Arc.dev",
        "type": "html",
        "url": "https://arc.dev/jobs",
    },
    {
        "name": "Turing",
        "type": "html",
        "url": "https://www.turing.com/careers",
    },
    {
        "name": "Remotebase",
        "type": "html",
        "url": "https://remotebase.com/careers",
    },
    {
        "name": "SuperAnnotate",
        "type": "lever",
        "slug": "superannotate",
    },
    {
        "name": "Toptal",
        "type": "html",
        "url": "https://www.toptal.com/careers",
    },
    # Crowdsourcing/AI training platforms
    {
        "name": "Outlier AI",
        "type": "html",
        "url": "https://outlier.ai/position",
    },
    {
        "name": "Invisible Technologies",
        "type": "html",
        "url": "https://www.invisibletext.com/careers",
    },
    {
        "name": "TELUS International AI",
        "type": "html",
        "url": "https://ai.telusinternational.com/collections/all-projects",
    },
    {
        "name": "OneForma",
        "type": "html",
        "url": "https://www.oneforma.com/jobs/",
    },
    {
        "name": "Toloka AI",
        "type": "html",
        "url": "https://toloka.ai/en/jobs",
    },
    {
        "name": "Welocalize",
        "type": "html",
        "url": "https://www.welocalize.com/careers/",
    },
    {
        "name": "Clickworker",
        "type": "html",
        "url": "https://www.clickworker.com/en/make-money/clickworker-jobs/",
    },
    {
        "name": "CrowdGen",
        "type": "html",
        "url": "https://crowdgen.com/projects",
    },
    {
        "name": "Quantigo AI",
        "type": "html",
        "url": "https://quantigo.ai/careers",
    },
    {
        "name": "OpenTrain AI",
        "type": "html",
        "url": "https://opentrain.ai/jobs",
    },
]


def fetch_remote_jobs(verbose: bool = True) -> list[dict]:
    """Fetch remote tech/CSE jobs from international platforms.

    Returns list of job dicts with source_site="remote_jobs".
    Jobs for Bangladesh get _is_bd_remote=True for badge display.
    """
    if verbose:
        print("  [remote_jobs] starting fetch...")

    all_jobs = []
    seen_urls: set[str] = set()

    for platform in REMOTE_PLATFORMS:
        name = platform["name"]
        ptype = platform["type"]
        try:
            if ptype == "greenhouse":
                jobs = _scrape_greenhouse(platform["board"], name)
            elif ptype == "lever":
                jobs = _scrape_lever(platform["slug"], name)
            elif ptype == "ashby":
                jobs = _scrape_ashby(platform["slug"], name)
            elif ptype == "smartrecruiters":
                jobs = _scrape_smartrecruiters(platform["identifier"], name)
            elif ptype == "html":
                jobs = _scrape_html_careers(platform["url"], name)
            else:
                continue

            kept = 0
            for job in jobs:
                url = job.get("posting_url") or ""
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                all_jobs.append(job)
                kept += 1

            if kept and verbose:
                print(f"  [remote_jobs] {name}: {kept} jobs")
            elif verbose:
                print(f"  [remote_jobs] {name}: 0 jobs")

            time.sleep(0.5)  # Be polite

        except Exception as e:
            if verbose:
                print(f"  [remote_jobs] {name}: failed ({e})")

    if verbose:
        print(f"  [remote_jobs] total: {len(all_jobs)} jobs")

    return all_jobs
