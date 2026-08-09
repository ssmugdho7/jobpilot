import random
import re
import time
from urllib.parse import urlparse, parse_qs, unquote, urljoin

import requests
from bs4 import BeautifulSoup

from app.config import load_search_config

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

HEADERS_BASE = {
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

SERP_SKIP_DOMAINS = {"google.com", "www.google.com", "gstatic.com", "googleusercontent.com"}


def _headers():
    headers = dict(HEADERS_BASE)
    headers["User-Agent"] = random.choice(USER_AGENTS)
    return headers


def _clean_url(url: str) -> str:
    if not url:
        return ""
    url = url.replace("\\x3d", "=").replace("\\x26", "&")
    # Resolve Google redirect links
    if url.startswith("/url?"):
        q = parse_qs(urlparse("https://www.google.com" + url).query)
        target = q.get("q", [""])[0]
        if target:
            return unquote(target)
        return ""
    if "www.google.com/url?" in url:
        q = parse_qs(urlparse(url).query)
        target = q.get("q", [""])[0]
        if target:
            return unquote(target)
        return ""
    return unquote(url)


def _snippet_from_link(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "")
    return text.strip()


def _parse_google(html: str, query: str, role: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen = set()

    for block in soup.select("a"):
        href = block.get("href", "")
        raw_url = _clean_url(href)
        if not raw_url:
            continue
        parsed = urlparse(raw_url)
        domain = (parsed.netloc or "").lower()
        if not domain or any(domain == d or domain.endswith("." + d) for d in SERP_SKIP_DOMAINS):
            continue
        if not parsed.scheme.startswith("http"):
            continue

        # Try to find the surrounding result container for title/snippet
        container = block
        for _ in range(4):
            container = container.parent
            if container is None:
                break
        title = ""
        h3 = container.select_one("h3") if container else None
        if h3:
            title = _snippet_from_link(h3.get_text())
        if not title:
            title = _snippet_from_link(block.get_text()) or raw_url[:120]

        snippet = ""
        if container:
            parts = [p.get_text(" ", strip=True) for p in container.select("span")]
            snippet = " ".join(parts)[:500]

        url_key = raw_url.split("#")[0]
        if url_key in seen:
            continue
        seen.add(url_key)

        results.append({
            "title": title,
            "url": raw_url,
            "source_site": domain,
            "snippet": snippet,
            "role": role,
            "query": query,
        })

    return results


def _parse_bing(html: str, query: str, role: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen = set()

    for li in soup.select("li.b_algo"):
        a = li.select_one("h2 a") or li.select_one("a")
        if not a:
            continue
        raw_url = a.get("href", "")
        if not raw_url:
            continue
        parsed = urlparse(raw_url)
        domain = (parsed.netloc or "").lower()
        if not domain:
            continue
        title = _snippet_from_link(a.get_text())
        snip_el = li.select_one(".b_caption p") or li.select_one("p")
        snippet = _snippet_from_link(snip_el.get_text()) if snip_el else ""
        url_key = raw_url.split("#")[0]
        if url_key in seen:
            continue
        seen.add(url_key)
        results.append({
            "title": title,
            "url": raw_url,
            "source_site": domain,
            "snippet": snippet,
            "role": role,
            "query": query,
        })
    return results


MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
)


def _looks_blocked(text: str, marker: str = "") -> bool:
    lowered = text.lower()
    if "unusual traffic" in lowered or "sorry/index" in lowered:
        return True
    if "turnstile" in lowered and "challenge" in lowered:
        return True
    # Visible challenge page rather than embedded script strings
    if marker and marker in lowered:
        return True
    return False


def search_google(query: str, role: str) -> list[dict]:
    params = {"q": query, "num": 10, "hl": "en"}
    try:
        resp = requests.get(
            "https://www.google.com/search",
            params=params,
            headers=_headers(),
            timeout=8,
        )
    except requests.RequestException:
        return []
    if resp.status_code != 200 or _looks_blocked(resp.text):
        return []
    return _parse_google(resp.text, query, role)


def search_bing(query: str, role: str) -> list[dict]:
    params = {"q": query, "count": 10, "mkt": "en-US", "setlang": "en"}
    headers = _headers()
    if "Android" not in headers.get("User-Agent", ""):
        headers["User-Agent"] = MOBILE_UA
    try:
        resp = requests.get(
            "https://www.bing.com/search",
            params=params,
            headers=headers,
            timeout=8,
        )
    except requests.RequestException:
        return []
    if resp.status_code != 200:
        return []
    # only treat as blocked when there are NO parseable results AND challenge markers
    parsed = _parse_bing(resp.text, query, role)
    if not parsed and _looks_blocked(resp.text, marker='class="b_algo"'):
        return []
    return parsed


def search_duckduckgo(query: str, role: str) -> list[dict]:
    try:
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers=_headers(),
            timeout=8,
        )
    except requests.RequestException:
        return []
    if resp.status_code != 200:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    results = []
    seen = set()
    for r in soup.select(".result"):
        a = r.select_one(".result__a")
        if not a:
            continue
        url = a.get("href", "")
        parsed = urlparse(url)
        domain = (parsed.netloc or "").lower()
        if not domain:
            continue
        snip_el = r.select_one(".result__snippet")
        url_key = url.split("#")[0]
        if url_key in seen:
            continue
        seen.add(url_key)
        results.append({
            "title": _snippet_from_link(a.get_text()),
            "url": url,
            "source_site": domain,
            "snippet": _snippet_from_link(snip_el.get_text()) if snip_el else "",
            "role": role,
            "query": query,
        })
    return results


def search_jobs(query: str, role: str) -> list[dict]:
    """Try Google, then Bing, then DuckDuckGo. Returns raw job dicts."""
    for engine in (search_google, search_bing, search_duckduckgo):
        results = engine(query, role)
        if results:
            return results
        time.sleep(random.uniform(0.5, 1.5))
    return []


def scan_all() -> list[dict]:
    """Run all configured roles/queries, return de-duplicated job dicts."""
    cfg = load_search_config()
    templates = cfg.get("query_templates", [])
    roles = cfg.get("roles", [])
    indicators = cfg.get("job_indicators", [])
    exclude_any = cfg.get("exclude_any", [])

    jobs: list[dict] = []
    seen_urls: set[str] = set()

    for role in roles:
        for template in templates:
            query = template.format(role=role)
            print(f"  [serp] {query}")
            for raw in search_jobs(query, role):
                text = f"{raw['title']} {raw['snippet']}".lower()
                if any(exc.lower() in text for exc in exclude_any):
                    continue
                if indicators and not any(ind.lower() in text for ind in indicators):
                    continue
                url_key = raw["url"].split("#")[0]
                if url_key in seen_urls:
                    continue
                seen_urls.add(url_key)
                jobs.append(raw)
            time.sleep(random.uniform(0.7, 1.6))

    print(f"  [serp] total jobs collected: {len(jobs)}")
    return jobs
