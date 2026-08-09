import json
import os
import re
import time
import threading
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()


def _load_keys() -> List[str]:
    """Load API keys from env. Supports:
    - GEMINI_API_KEYS (comma-separated list)
    - GEMINI_API_KEY_1, GEMINI_API_KEY_2, ...
    - fallback to single GEMINI_API_KEY
    """
    # 1. Comma-separated list
    raw = os.getenv("GEMINI_API_KEYS", "").strip()
    if raw:
        return [k.strip() for k in raw.split(",") if k.strip()]

    # 2. Numbered keys
    keys = []
    i = 1
    while True:
        k = os.getenv(f"GEMINI_API_KEY_{i}", "").strip()
        if not k:
            break
        keys.append(k)
        i += 1
    if keys:
        return keys

    # 3. Single key fallback
    single = os.getenv("GEMINI_API_KEY", "").strip()
    return [single] if single else []


_KEYS = _load_keys()
_KEY_INDEX = 0
_KEY_STATE = {k: {"failures": 0, "last_used": 0.0} for k in _KEYS}
_KEY_LOCK = threading.Lock()


def _next_key() -> Optional[str]:
    """Return the next available key, skipping exhausted ones."""
    if not _KEYS:
        return None
    with _KEY_LOCK:
        for offset in range(len(_KEYS)):
            idx = (_KEY_INDEX + offset) % len(_KEYS)
            k = _KEYS[idx]
            if _KEY_STATE[k]["failures"] < 3:  # skip permanently failed keys
                return k
    return None


def get_client():
    from google import genai

    key = _next_key()
    if not key:
        return None
    try:
        return genai.Client(api_key=key), key
    except Exception:
        return None, None


def get_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")


def gemini_available() -> bool:
    return bool(_KEYS)


def _retry_delay(err_msg: str) -> float:
    m = re.search(r"retryDelay':\s*'(\d+)s", err_msg)
    if not m:
        return 8.0
    # Daily free-tier quota is exhausted — retrying is pointless.
    if "RequestsPerDayPerProjectPerModel" in err_msg:
        return -1
    # Cap waits so a half-rate-limited key still fails fast into the fallback.
    return min(float(m.group(1)) + 1, 15.0)


def _mark_failure(key: str, is_quota_exhausted: bool):
    with _KEY_LOCK:
        if key in _KEY_STATE:
            _KEY_STATE[key]["failures"] += 1
            if is_quota_exhausted:
                _KEY_STATE[key]["failures"] = 10  # mark as exhausted for the day
        # rotate index
        global _KEY_INDEX
        if _KEYS:
            _KEY_INDEX = (_KEYS.index(key) + 1) % len(_KEYS)


def _generate_text(prompt: str, *, json_mode: bool = False, temperature: float = 0.4) -> str:
    if not _KEYS:
        raise RuntimeError("No Gemini API keys configured (set GEMINI_API_KEYS in .env)")

    last_err = None
    tried_keys = set()

    while True:
        client, key = get_client()
        if client is None or key is None or key in tried_keys:
            # all keys exhausted or tried
            break

        tried_keys.add(key)
        config = {"temperature": temperature}
        if json_mode:
            config["response_mime_type"] = "application/json"

        try:
            response = client.models.generate_content(
                model=get_model(), contents=prompt, config=config
            )
            return (response.text or "").strip()
        except Exception as e:
            err_str = str(e)
            last_err = e
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                wait = _retry_delay(err_str)
                is_quota = "RequestsPerDayPerProjectPerModel" in err_str
                _mark_failure(key, is_quota)
                if wait < 0:
                    # quota exhausted, try next key immediately
                    print(f"  [gemini] key exhausted, rotating to next key...")
                    continue
                print(f"  [gemini] rate limited; retrying in {wait:.0f}s...")
                time.sleep(wait)
                continue
            raise

    raise RuntimeError(f"Gemini request failed (all keys exhausted): {last_err}")


def generate_json(prompt: str, temperature: float = 0.3) -> dict:
    text = _generate_text(prompt, json_mode=True, temperature=temperature)
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)
