import re
from app.config import load_search_config

# Role -> keywords that strongly indicate the role (matched against title+snippet)
# Order matters: more specific roles first, "software engineer" as the catch-all last.
ROLE_KEYWORDS = {
    "ai engineer": [
        "ai engineer", "ai developer", "artificial intelligence", "machine learning engineer",
        "llm", "genai", "generative ai", "nlp", "computer vision", "deep learning",
        "prompt engineer", "data scientist", "ml engineer", "mlops",
    ],
    "qa analyst": [
        "qa analyst", "quality analyst", "quality assurance", "test engineer",
        "qa engineer", "qa automation", "automation engineer", "software tester",
        "manual tester", "test analyst", "qa",
    ],
    "data analyst": [
        "data analyst", "data analytics", "bi analyst", "business intelligence",
        "power bi", "tableau", "data analysis", "analyst - bi", "analytics engineer",
    ],
    "app developer": [
        "app developer", "mobile developer", "mobile app", "android developer",
        "ios developer", "react native", "flutter", "xamarin", "kotlin", "swift developer",
        "dart developer", "mobile engineer", "app engineer",
    ],
    "devops or cloud engineer": [
        "devops", "cloud engineer", "cloud architect", "site reliability", "sre",
        "ci/cd", "kubernetes", "docker", "terraform", "aws engineer", "azure engineer",
        "gcp", "platform engineer", "infrastructure engineer",
    ],
    "it executive": [
        "it executive", "it officer", "it admin", "it administrator", "it specialist",
        "system administrator", "system admin", "network administrator", "network engineer",
        "it support", "help desk", "helpdesk", "it helpdesk", "executive - it", "executive, it",
    ],
    "web developer": [
        "web developer", "frontend", "front-end", "front end", "react", "vue", "angular",
        "wordpress", "php", "laravel", "html", "css", "javascript", "typescript",
        "next.js", "nextjs", "django", "full stack developer", "web designer",
    ],
    "software engineer": [
        "software engineer", "software developer", "backend", "back end", "full stack",
        "fullstack", "full-stack", "programmer", "c#", ".net", "dotnet", "java developer",
        "python developer", "spring boot", "node.js", "nodejs", "golang", "go developer",
        "ruby developer", "api developer", "software",
    ],
}

ROLE_ORDER = list(ROLE_KEYWORDS.keys())


def _get_all_roles() -> dict:
    """Return all roles including custom ones from config."""
    cfg = load_search_config()
    custom = cfg.get("custom_roles") or []
    all_roles = dict(ROLE_KEYWORDS)
    for cr in custom:
        cr_lower = cr.lower().strip()
        if cr_lower and cr_lower not in all_roles:
            # Custom role uses its own name as keyword
            all_roles[cr_lower] = [cr_lower]
    return all_roles


def _get_role_order() -> list:
    """Return role order with custom roles first."""
    cfg = load_search_config()
    custom = cfg.get("custom_roles") or []
    custom_lower = [cr.lower().strip() for cr in custom if cr.strip()]
    return custom_lower + ROLE_ORDER


def detect_role(job: dict) -> str:
    """Return the role best matching a job, or '' if it matches none."""
    title = (job.get("title") or "").lower()
    snippet = (job.get("snippet") or "").lower()
    company = (job.get("company") or "").lower()
    text = f"{title} {snippet} {company}"
    text = re.sub(r"[\s]+", " ", text)

    all_roles = _get_all_roles()
    role_order = _get_role_order()

    best_role, best_hits = "", 0
    for role in role_order:
        keywords = all_roles.get(role, [])
        hits = 0
        for kw in keywords:
            if kw in text:
                hits += 1
        # a match inside the title counts double
        for kw in keywords:
            if kw in title:
                hits += 1
        if hits > best_hits:
            best_role, best_hits = role, hits
    return best_role


def score_job(job: dict) -> float:
    """Return a relevance score in [0,1] for a job against its role."""
    role = job.get("role") or detect_role(job)
    if not role:
        return 0.0
    all_roles = _get_all_roles()
    role_kw = all_roles.get(role, [])

    title = (job.get("title") or "").lower()
    snippet = (job.get("snippet") or "").lower()
    text = f"{title} {snippet}"

    score = 0.3
    for kw in role_kw:
        if kw in text:
            score += 0.2
    for kw in role_kw:
        if kw in title:
            score += 0.3
    return round(min(score, 1.0), 2)


def is_relevant(job: dict, min_score: float = 0.0) -> bool:
    role = job.get("role") or detect_role(job)
    return bool(role) and score_job(job) >= min_score
