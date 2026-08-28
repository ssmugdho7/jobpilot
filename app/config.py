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
