"""Bangladesh job sources — BDJobs (SSR page) + LinkedIn (jobs in Bangladesh).

Both sources are reachable without a key and return recent Bangladesh postings
with a publish date, which drives the "posted within 1d/3d/1w/1m" filter.
"""

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs, urlencode, urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from app.config import load_search_config, load_careers_config

load_dotenv()

BDJOBS_GATEWAY = "https://gateway.bdjobs.com/joblist/jobs"
BDJOBS_JOB_URL = "https://jobs.bdjobs.com/jobdetails/?id={job_id}"

LINKEDIN_SEARCH_URL = "https://www.linkedin.com/jobs/search/"

FACEBOOK_GRAPH = "https://graph.facebook.com/v21.0"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Role -> LinkedIn search keyword(s). More terms = more results per role.
ROLE_SEARCH_TERMS = {
    "web developer": ["web developer", "frontend developer", "php laravel"],
    "ai engineer": ["ai engineer", "machine learning engineer", "data scientist"],
    "it executive": ["IT executive", "system administrator", "IT support engineer"],
    "software engineer": ["software engineer", "backend developer", "full stack developer"],
    "devops or cloud engineer": ["devops engineer", "cloud engineer", "site reliability engineer"],
    "qa analyst": ["QA engineer", "QA analyst", "software tester"],
    "data analyst": ["data analyst", "business intelligence", "power bi"],
    "app developer": ["android developer", "flutter developer", "mobile app developer"],
}


def _get_search_terms() -> dict:
    """Return search terms including custom roles from config."""
    cfg = load_search_config()
    custom = cfg.get("custom_roles") or []
    terms = dict(ROLE_SEARCH_TERMS)
    for cr in custom:
        cr_lower = cr.lower().strip()
        if cr_lower and cr_lower not in terms:
            terms[cr_lower] = [cr_lower]
    return terms


_BD_NG_STATE_RE = re.compile(r'<script id="ng-state" type="application/json">(.*?)</script>', re.S)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# Bangladesh city/district hints used to accept a posting's location.
_BD_PLACES = [
    "bangladesh", "dhaka", "chittagong", "chattogram", "sylhet", "rajshahi",
    "khulna", "barisal", "rangpur", "comilla", "cumilla", "gazipur",
    "narayanganj", "mymensingh", "savar", "tongi", "uttara", "gulshan",
    "bashundhara", "bogra", "jashore", "kushtia", "mymensingh", "cox",
    "bagerhat", "bhola", "barguna", "bandarban", "brahmanbaria", "chandpur",
    "chuadanga", "dinajpur", "faridpur", "feni", "gaibandha", "habiganj",
    "joypurhat", "kishoreganj", "kurigram", "lakshmipur", "lalmonirhat",
    "madaripur", "magura", "manikganj", "meherpur", "moulvibazar", "munshiganj",
    "naogaon", "natore", "nawabganj", "netrokona", "nilphamari", "noakhali",
    "pabna", "panchagarh", "patuakhali", "pirojpur", "sirajganj", "satkhira",
    "shariatpur", "sherpur", "sunamganj", "tangail", "thakurgaon", "srimangal",
    "mirpur", "banani", "dhanmondi", "bashundhara", "uttam", "anywhere in bangladesh",
]

# Countries/places clearly NOT Bangladesh — a location mentioning any of these
# (without a Bangladeshi hint) is dropped.
_NON_BD_PLACES = [
    "united states", " usa", "united kingdom", " uk ", " london", "uae", "dubai",
    "abu dhabi", "saudi", "qatar", "oman", "bahrain", "kuwait", "singapore",
    "malaysia", "india", "pakistan", "nepal", "sri lanka", "vietnam", "philippines",
    "indonesia", "thailand", "china", "japan", "south korea", "germany", "france",
    "canada", "australia", "new zealand", "turkey", "nigeria", "kenya", "egypt",
    "brazil", "mexico", "europe", "poland", "netherlands", "sweden", "norway",
    "finland", "denmark", "ireland", "spain", "italy", "austria", "belgium",
    "switzerland", "doha", "riyadh", "jeddah", "muscat", "hong kong",
]


def _is_bangladesh_location(location: str) -> bool:
    """Return True only if location explicitly mentions Bangladesh or a BD city/district.
    Global/remote jobs without explicit Bangladesh mention are rejected."""
    loc = (location or "").lower()
    if not loc.strip():
        return False
    return any(p in loc for p in _BD_PLACES)


def _clean_html(text: str) -> str:
    if not text:
        return ""
    text = _HTML_TAG_RE.sub(" ", str(text))
    return _WS_RE.sub(" ", text).strip()


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _norm(text: str) -> str:
    return _WS_RE.sub(" ", (text or "")).strip()


# ---------------------------------------------------------------------------
# BDJobs
# ---------------------------------------------------------------------------

def _ng_state_jobs(html: str) -> list[dict]:
    m = _BD_NG_STATE_RE.search(html)
    if not m:
        return []
    try:
        state = json.loads(m.group(1))
    except Exception:
        return []
    jobs: list[dict] = []
    seen = set()
    for node in state.values():
        if not isinstance(node, dict):
            continue
        body = node.get("b") or {}
        records = body.get("data")
        if not isinstance(records, list):
            continue
        for rec in records:
            if not isinstance(rec, dict) or not rec.get("jobTitle"):
                continue
            job_id = str(rec.get("Jobid") or "")
            if not job_id or job_id in seen:
                continue
            seen.add(job_id)
            jobs.append(rec)
    return jobs


def fetch_bdjobs(max_pages: int | None = None) -> list[dict]:
    cfg = load_search_config()
    if max_pages is None:
        max_pages = int(cfg.get("bdjobs_max_pages", 3))
    results: list[dict] = []
    seen = set()

    for page in range(1, max_pages + 1):
        try:
            resp = requests.get(
                BDJOBS_GATEWAY,
                params={"pageNo": page, "fcatId": 8},
                headers=HEADERS,
                timeout=25,
            )
            if resp.status_code != 200:
                continue
        except Exception as e:
            print(f"  [bdjobs] page {page} failed: {e}")
            continue
        except Exception as e:
            print(f"  [bdjobs] page {page} failed: {e}")
            continue

        records = _ng_state_jobs(resp.text)
        if not records:
            continue

        for rec in records:
            job_id = str(rec.get("Jobid") or "")
            if not job_id or job_id in seen:
                continue
            seen.add(job_id)

            posted = _parse_iso(rec.get("publishDate"))
            deadline = _parse_iso(rec.get("deadlineDB"))
            location = _norm(rec.get("location"))
            salary = _norm(rec.get("Salary") or "--")
            snippet = _clean_html(
                " ".join(filter(None, [
                    rec.get("jobDescription"),
                    rec.get("eduRec"),
                    rec.get("jobContext"),
                    rec.get("experience"),
                ]))
            )
            if not snippet:
                snippet = f"{rec.get('jobTitle')} - {rec.get('companyName')}"

            results.append({
                "title": _norm(rec.get("jobTitle")),
                "company": _norm(rec.get("companyName")),
                "location": f"{location}, Bangladesh" if location and "bangladesh" not in location.lower() else (location or "Bangladesh"),
                "source_site": "bdjobs.com",
                "posting_url": BDJOBS_JOB_URL.format(job_id=job_id),
                "snippet": snippet[:1000],
                "posted_date": posted,
                "deadline": deadline,
                "salary": salary,
            })

    if results:
        print(f"  [bdjobs] collected {len(results)} jobs")
    return results


# ---------------------------------------------------------------------------
# LinkedIn (Bangladesh)
# ---------------------------------------------------------------------------

def _linkedin_tpr(days: int) -> str:
    if days <= 1:
        return "r86400"
    if days <= 3:
        return "r259200"
    if days <= 7:
        return "r604800"
    return "r2592000"


def _clean_linkedin_url(url: str) -> str:
    return (url or "").split("?")[0]


def _fetch_linkedin_term(term: str, tpr: str) -> list[dict]:
    try:
        resp = requests.get(
            LINKEDIN_SEARCH_URL,
            params={
                "keywords": term,
                "location": "Bangladesh",
                "f_TPR": tpr,
            },
            headers=HEADERS,
            timeout=12,
        )
        if resp.status_code != 200:
            return []
    except Exception as e:
        print(f"  [linkedin:{term}] failed: {e}")
        return []

    soup = BeautifulSoup(resp.content, "html.parser")
    cards = soup.select(".base-card, .job-search-card, .base-search-card")
    found: list[dict] = []
    for card in cards:
        try:
            link_el = card.select_one('a[href*="/jobs/view/"]')
            if not link_el:
                continue
            posting_url = _clean_linkedin_url(link_el.get("href", ""))
            if not posting_url:
                continue

            title_el = card.select_one(
                ".base-search-card__title, .job-search-card__title, h3"
            )
            company_el = card.select_one(
                ".base-search-card__subtitle, .job-search-card__subtitle, h4"
            )
            location_el = card.select_one(".job-search-card__location")
            time_el = card.select_one(
                "time.job-search-card__listdate--new, time"
            )

            title = _norm(title_el.get_text(" ", strip=True)) if title_el else ""
            company = _norm(company_el.get_text(" ", strip=True)) if company_el else ""
            location = _norm(location_el.get_text(" ", strip=True)) if location_el else "Bangladesh"
            date_str = time_el.get("datetime", "") if time_el else ""
            posted = _parse_iso(date_str)

            if not title:
                continue
            if not _is_bangladesh_location(location):
                continue
            raw_text = card.get_text(" ", strip=True)

            found.append({
                "title": title,
                "company": company,
                "location": location,
                "source_site": "linkedin.com",
                "posting_url": posting_url,
                "snippet": _norm(raw_text)[:400],
                "posted_date": posted,
                "deadline": None,
                "salary": None,
            })
        except Exception:
            continue
    return found


def fetch_linkedin(max_age_days: int | None = None) -> list[dict]:
    if max_age_days is None:
        cfg = load_search_config()
        max_age_days = int(cfg.get("max_age_days", 30))
    tpr = _linkedin_tpr(max_age_days)

    tasks = []
    for role, terms in ROLE_SEARCH_TERMS.items():
        for term in terms:
            tasks.append((role, term))

    per_role: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_linkedin_term, term, tpr): (role, term) for role, term in tasks}
        for fut in futures:
            role, term = futures[fut]
            try:
                for job in fut.result():
                    job["_role"] = role
                    per_role.setdefault(role, []).append(job)
            except Exception as e:
                print(f"  [linkedin:{term}] failed: {e}")

    results: list[dict] = []
    seen = set()
    for role in per_role:
        for job in per_role[role]:
            url = job["posting_url"]
            if url in seen:
                continue
            seen.add(url)
            results.append(job)

    if results:
        print(f"  [linkedin] collected {len(results)} jobs")
    return results


# ---------------------------------------------------------------------------
# Facebook job posts (Graph API) — needs FACEBOOK_ACCESS_TOKEN in .env
# ---------------------------------------------------------------------------

def facebook_enabled() -> bool:
    cfg = load_search_config()
    has_token = bool((os.getenv("FACEBOOK_ACCESS_TOKEN") or "").strip())
    has_targets = bool(cfg.get("facebook_groups") or cfg.get("facebook_pages"))
    return has_token and has_targets


def _facebook_parse_dt(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _facebook_title(msg: str, attachment: dict | None) -> str:
    attach_title = ((attachment or {}).get("title") or "").strip()
    if attach_title and len(attach_title) > 4:
        return attach_title[:120]
    first_line = ""
    for ln in (msg or "").splitlines():
        ln = ln.strip()
        if ln:
            first_line = ln
            break
    return first_line[:120] or "Facebook job post"


def _facebook_looks_like_job(text: str, terms: list[str]) -> bool:
    low = (text or "").lower()
    return any(t in low for t in terms)


def _facebook_posts(group_id: str, is_page: bool, token: str, terms: list[str]) -> list[dict]:
    edge = "posts" if is_page else "feed"
    url = f"{FACEBOOK_GRAPH}/{group_id}/{edge}"
    try:
        resp = requests.get(
            url,
            params={
                "fields": "message,created_time,permalink_url,id,"
                          "attachments{title,url,description,media_type}",
                "limit": "50",
                "access_token": token,
            },
            headers=HEADERS,
            timeout=20,
        )
        if resp.status_code != 200:
            err = (resp.json() or {}).get("error", {}).get("message", "")
            print(f"  [facebook] {group_id} HTTP {resp.status_code}: {err[:80]}")
            return []
    except Exception as e:
        print(f"  [facebook] {group_id} failed: {e}")
        return []

    data = (resp.json() or {}).get("data") or []
    found: list[dict] = []
    for post in data:
        msg = (post.get("message") or "").strip()
        if not msg:
            continue
        if not _facebook_looks_like_job(msg, terms):
            continue
        permalink = post.get("permalink_url") or ""
        if not permalink:
            continue
        location = "Bangladesh"
        if not _is_bangladesh_location(msg):
            continue
        attach = None
        atts = post.get("attachments") or {}
        data_atts = atts.get("data") or []
        if data_atts:
            attach = data_atts[0]
            if not msg and (attach.get("title") or "").strip():
                msg = (attach.get("title") or "")[:400]
        found.append({
            "title": _facebook_title(msg, attach),
            "company": "Facebook post",
            "location": location,
            "source_site": "facebook.com",
            "posting_url": permalink,
            "snippet": msg[:1000],
            "posted_date": _facebook_parse_dt(post.get("created_time") or ""),
            "deadline": None,
            "salary": None,
            "_role": None,
        })
    return found


def fetch_facebook() -> list[dict]:
    """Pull job posts from configured Facebook groups/pages via the Graph API.

    Requires FACEBOOK_ACCESS_TOKEN in .env. Skips quietly when the token is
    missing (Facebook blocks all anonymous scraping from this network).
    """
    if not facebook_enabled():
        cfg = load_search_config()
        has_token = bool((os.getenv("FACEBOOK_ACCESS_TOKEN") or "").strip())
        has_targets = bool(cfg.get("facebook_groups") or cfg.get("facebook_pages"))
        if not has_token:
            print("  [facebook] skipped (no FACEBOOK_ACCESS_TOKEN set)")
        else:
            print("  [facebook] skipped (no groups/pages configured in config/search.yaml)")
        return []
    cfg = load_search_config()
    token = os.getenv("FACEBOOK_ACCESS_TOKEN", "").strip()
    terms = [t.lower() for t in cfg.get("facebook_terms") or []]
    targets = [(g, False) for g in cfg.get("facebook_groups") or []]
    targets += [(p, True) for p in cfg.get("facebook_pages") or []]
    if not targets or not terms:
        return []

    results: list[dict] = []
    seen = set()
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_facebook_posts, tid, page, token, terms) for tid, page in targets]
        for fut in futures:
            try:
                for job in fut.result():
                    if job["posting_url"] in seen:
                        continue
                    seen.add(job["posting_url"])
                    results.append(job)
            except Exception as e:
                print(f"  [facebook] fetch failed: {e}")

    if results:
        print(f"  [facebook] collected {len(results)} job posts")
    return results


# ---------------------------------------------------------------------------
# Company career pages (software / telecom / IT — startup, MNC, private, gov)
# ---------------------------------------------------------------------------

_JOB_HREF_RE = re.compile(r"(/job[s]?|/position|/opening|/vacanc|/posting|job\.aspx)", re.I)
_NAV_LINK_TEXTS = {
    "career", "careers", "view job", "view more", "view all openings",
    "explore open roles", "explore opportunities", "hiring", "explore jobs",
    "see all jobs", "apply now", "view jobs", "all jobs", "open positions",
    "view all jobs", "career opportunities", "join us", "why join us",
    "career advice", "career opportunities", "learn more",
    "browse all jobs", "browse jobs", "view all", "see all",
    "jobs", "job", "we are hiring", "we're hiring", "hiring now",
    "current openings", "open positions", "available positions",
    "job openings", "vacancies", "vacancy",
}
_NAV_HREF_ROOTS = re.compile(r"/career[s]?$|/career/s?$|/career/#|/careers/$", re.I)


def _html_career_jobs(company: dict) -> list[dict]:
    """Parse a static HTML career page for job links (links in /jobs/<slug> paths)."""
    url = company.get("careers_url") or ""
    if not url:
        return []
    resp = requests.get(url, headers=HEADERS, timeout=20)
    if resp.status_code != 200:
        return []
    soup = BeautifulSoup(resp.content, "html.parser")

    found: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        text = a.get_text(" ", strip=True)
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        if not _JOB_HREF_RE.search(href):
            continue
        posting_url = urljoin(url, href).split("#")[0].split("?")[0]
        # skip the careers list page itself or bare navigation roots
        if posting_url.rstrip("/") == url.rstrip("/"):
            continue
        if _NAV_HREF_ROOTS.search(posting_url):
            continue
        low_text = re.sub(r"\s+", " ", text.strip().lower()).strip("·•").strip()
        if not low_text or low_text in _NAV_LINK_TEXTS:
            continue
        title = re.sub(r"\s+", " ", text).strip()[:120]
        if not title or len(title) < 4:
            continue
        if posting_url in found:
            continue
        found[posting_url] = {
            "title": title,
            "company": company.get("name") or urlparse(posting_url).netloc,
            "location": company.get("location") or "Bangladesh",
            "source_site": company.get("site") or urlparse(posting_url).netloc,
            "posting_url": posting_url,
            "snippet": title,
            "posted_date": None,
            "deadline": None,
            "salary": None,
        }
    return list(found.values())


def _smartrecruiters_jobs(company: dict) -> list[dict]:
    identifier = company.get("identifier") or ""
    if not identifier:
        return []
    resp = requests.get(
        f"https://api.smartrecruiters.com/v1/companies/{identifier}/postings",
        params={"limit": "100", "offset": "0"},
        headers=HEADERS,
        timeout=20,
    )
    if resp.status_code != 200:
        return []
    data = (resp.json() or {}).get("content") or []
    results: list[dict] = []
    for post in data:
        name = (post.get("name") or "").strip()
        if not name:
            continue
        loc = post.get("location") or {}
        loc_str = ", ".join(filter(None, [loc.get("city"), loc.get("region"), loc.get("country")]))
        if not _is_bangladesh_location(loc_str or (loc.get("country") or "Bangladesh")):
            continue
        post_id = post.get("id") or post.get("refNumber") or ""
        if post_id:
            posting_url = f"https://jobs.smartrecruiters.com/{identifier}/{post_id}"
        else:
            posting_url = ""
        snippet = ""
        try:
            snippet = (post.get("jobAd", {}).get("sections", {}).get("jobDescription", {}) or {}).get("text", "") or ""
        except Exception:
            snippet = ""
        results.append({
            "title": name,
            "company": company.get("name") or identifier,
            "location": loc_str or "Bangladesh",
            "source_site": company.get("site") or "smartrecruiters.com",
            "posting_url": posting_url,
            "snippet": (snippet or name)[:1000],
            "posted_date": None,  # career pages: position is open until removed
            "deadline": None,
            "salary": None,
        })
    return results


def _greenhouse_jobs(company: dict) -> list[dict]:
    board = company.get("board") or ""
    if not board:
        return []
    resp = requests.get(
        f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs",
        params={"content": "true"},
        headers=HEADERS,
        timeout=20,
    )
    if resp.status_code != 200:
        return []
    jobs = (resp.json() or {}).get("jobs") or []
    results: list[dict] = []
    for job in jobs:
        title = (job.get("title") or "").strip()
        location = (job.get("location") or {}).get("name") or ""
        if not title or not _is_bangladesh_location(location or "Bangladesh"):
            continue
        snippet = re.sub(r"<[^>]+>", " ", job.get("content") or title)
        results.append({
            "title": title,
            "company": company.get("name") or board,
            "location": location or "Bangladesh",
            "source_site": company.get("site") or "greenhouse.io",
            "posting_url": job.get("absolute_url") or "",
            "snippet": _WS_RE.sub(" ", snippet).strip()[:1000],
            "posted_date": _parse_iso(job.get("updated_at")),
            "deadline": None,
            "salary": None,
        })
    return [r for r in results if r["posting_url"]]


def _lever_jobs(company: dict) -> list[dict]:
    slug = company.get("slug") or ""
    if not slug:
        return []
    resp = requests.get(
        f"https://api.lever.co/v0/postings/{slug}?mode=json",
        headers=HEADERS,
        timeout=20,
    )
    if resp.status_code != 200:
        return []
    data = resp.json()
    if not isinstance(data, list):
        return []
    results: list[dict] = []
    for post in data:
        title = (post.get("text") or "").strip()
        cats = post.get("categories") or {}
        location = cats.get("location") or "Bangladesh"
        if not title or not _is_bangladesh_location(location):
            continue
        results.append({
            "title": title,
            "company": company.get("name") or slug,
            "location": location,
            "source_site": company.get("site") or "lever.co",
            "posting_url": post.get("hostedUrl") or "",
            "snippet": (post.get("descriptionPlain") or title)[:1000],
            "posted_date": _parse_iso(post.get("createdAt")),
            "deadline": None,
            "salary": None,
        })
    return [r for r in results if r["posting_url"]]


def _ashby_jobs(company: dict) -> list[dict]:
    slug = company.get("slug") or ""
    if not slug:
        return []
    query = (
        "query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {"
        " jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) {"
        "   jobPostings { id title locationName employmentType }"
        " }"
        "}"
    )
    resp = requests.post(
        "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams",
        json={
            "operationName": "ApiJobBoardWithTeams",
            "variables": {"organizationHostedJobsPageName": slug},
            "query": query,
        },
        headers={"Content-Type": "application/json", **HEADERS},
        timeout=20,
    )
    if resp.status_code != 200:
        return []
    board = ((resp.json() or {}).get("data") or {}).get("jobBoardWithTeams") or {}
    postings = board.get("jobPostings") or []
    results: list[dict] = []
    for post in postings:
        title = (post.get("title") or "").strip()
        location = post.get("locationName") or "Bangladesh"
        if not title or not _is_bangladesh_location(location):
            continue
        results.append({
            "title": title,
            "company": company.get("name") or slug,
            "location": location,
            "source_site": company.get("site") or "ashbyhq.com",
            "posting_url": f"https://jobs.ashbyhq.com/{slug}/{post.get('id')}",
            "snippet": title,
            "posted_date": None,
            "deadline": None,
            "salary": None,
        })
    return results


def fetch_careers() -> list[dict]:
    """Fetch jobs from configured company career pages (see config/careers.yaml)."""
    cfg = load_careers_config()
    companies = cfg.get("companies") or []
    if not companies:
        return []

    results: list[dict] = []
    seen = set()
    for company in companies:
        ctype = (company.get("type") or "").lower()
        try:
            if ctype == "html":
                jobs = _html_career_jobs(company)
            elif ctype == "smartrecruiters":
                jobs = _smartrecruiters_jobs(company)
            elif ctype == "greenhouse":
                jobs = _greenhouse_jobs(company)
            elif ctype == "lever":
                jobs = _lever_jobs(company)
            elif ctype == "ashby":
                jobs = _ashby_jobs(company)
            else:
                print(f"  [careers] {company.get('name')}: unknown type '{ctype}'")
                continue
            kept = 0
            for job in jobs:
                url = job.get("posting_url") or ""
                if not url or url in seen:
                    continue
                seen.add(url)
                results.append(job)
                kept += 1
            if kept:
                print(f"  [careers] {company.get('name')}: {kept} jobs")
        except Exception as e:
            print(f"  [careers] {company.get('name')}: failed ({e})")

    return results


# ---------------------------------------------------------------------------

def fetch_bangladesh_jobs(max_age_days: int | None = None) -> list[dict]:
    """Collect Bangladesh IT jobs from BDJobs + LinkedIn (BD) + company career pages."""
    if max_age_days is None:
        cfg = load_search_config()
        max_age_days = int(cfg.get("max_age_days", 30))
    jobs = fetch_bdjobs()
    jobs.extend(fetch_linkedin(max_age_days))
    jobs.extend(fetch_careers())
    jobs.extend(fetch_facebook())
    return jobs
