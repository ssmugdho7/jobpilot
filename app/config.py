import os
import sys
import yaml
from app.paths import CONFIG_DIR

sys.stdout.reconfigure(encoding="utf-8")


def load_search_config() -> dict:
    path = os.path.join(CONFIG_DIR, "search.yaml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_careers_config() -> dict:
    path = os.path.join(CONFIG_DIR, "careers.yaml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_fb_post_search_config() -> dict:
    """Load Facebook Post Search config (YAML + env overrides)."""
    path = os.path.join(CONFIG_DIR, "fb_post_search.yaml")
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        cfg = {}

    # Env overrides
    if os.getenv("SERPER_API_KEY"):
        cfg["serper_api_key"] = os.getenv("SERPER_API_KEY", "").strip()
    env_enabled = os.getenv("FB_POST_SEARCH_ENABLED")
    if env_enabled is not None:
        cfg["_env_enabled"] = env_enabled.strip().lower() in ("1", "true", "yes", "on")

    # Defaults
    cfg.setdefault("enabled", True)
    cfg.setdefault("tbs", "qdr:d")
    cfg.setdefault("max_age_days", 3)
    cfg.setdefault("queries", [])
    cfg.setdefault("allowed_domains", ["facebook.com", "m.facebook.com", "web.facebook.com", "*.facebook.com"])
    cfg.setdefault("title_filter_keywords", [
        "hiring", "we're hiring", "we are hiring", "job circular", "vacancy",
        "software engineer", "developer", "full stack", "backend", "frontend",
        "ai engineer", "ml engineer", "devops engineer", "sqa", "qa engineer",
        "project manager", "laravel", "web developer", "data analyst",
    ])
    cfg.setdefault("location_keywords", ["dhaka", "bangladesh"])
    cfg.setdefault("max_queries_per_run", 5)
    cfg.setdefault("results_per_query", 10)
    cfg.setdefault("delay_between_queries", 1.5)
    cfg.setdefault("request_timeout", 15)
    return cfg
