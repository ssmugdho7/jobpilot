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
    """Load Facebook Graph API config (YAML + env overrides)."""
    path = os.path.join(CONFIG_DIR, "fb_post_search.yaml")
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        cfg = {}

    # Env overrides
    if os.getenv("FACEBOOK_ACCESS_TOKEN"):
        cfg["access_token"] = os.getenv("FACEBOOK_ACCESS_TOKEN", "").strip()
    env_enabled = os.getenv("FB_POST_SEARCH_ENABLED")
    if env_enabled is not None:
        cfg["_env_enabled"] = env_enabled.strip().lower() in ("1", "true", "yes", "on")

    # Defaults
    cfg.setdefault("enabled", True)
    cfg.setdefault("max_age_days", 3)
    cfg.setdefault("search_queries", [
        "jobs bangladesh",
        "hiring bangladesh",
        "vacancy dhaka",
        "career bangladesh",
    ])
    cfg.setdefault("max_pages_per_run", 10)
    cfg.setdefault("posts_per_page", 20)
    return cfg
