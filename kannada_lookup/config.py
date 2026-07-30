"""Configuration: .env for secrets, data/settings.json for user choices.

.env (copy .env.example, or let the first-run dialog create it) holds the
API key — never hardcoded, never committed. settings.json holds the
one-time setup answers (target language); its absence IS the first-run
signal.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

from . import languages

# .env lives in the project root (one level above this package).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
SETTINGS_PATH = PROJECT_ROOT / "data" / "settings.json"
load_dotenv(ENV_PATH)


# --- One-time setup (first-run dialog) ------------------------------------

def load_settings() -> dict | None:
    """Parsed settings.json, or None → first run, show the setup dialog."""
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_settings(target_language: str) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps({"target_language": target_language}, indent=2),
        encoding="utf-8",
    )
    refresh_language()


def save_api_key(key: str) -> None:
    """Write the Gemini key into .env (create or append). Called by the
    first-run dialog so cloned installs need zero manual file editing."""
    lines = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
        lines = [l for l in lines if not l.startswith("GEMINI_API_KEY=")]
    lines += [f"GEMINI_API_KEY={key.strip()}", "PROVIDER=gemini"]
    # De-dup PROVIDER lines while preserving everything else.
    seen_provider = False
    out = []
    for l in lines:
        if l.startswith("PROVIDER="):
            if seen_provider:
                continue
            seen_provider = True
        out.append(l)
    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.environ["GEMINI_API_KEY"] = key.strip()
    global GEMINI_API_KEY
    GEMINI_API_KEY = key.strip()


def refresh_language() -> None:
    """Re-read the language after the setup dialog saves it (config is
    imported before the dialog runs)."""
    global TARGET_LANGUAGE, TARGET_LANG, LANGUAGE_GLYPH
    settings = load_settings() or {}
    TARGET_LANGUAGE = settings.get("target_language", "Kannada")
    entry = languages.get(TARGET_LANGUAGE)
    TARGET_LANG = entry["code"] or "kn"   # legacy Google-provider ISO code
    LANGUAGE_GLYPH = entry["glyph"]

# --- Provider -----------------------------------------------------------
# "gemini" (default): Gemini API with a free Google AI Studio key —
#   meaning + example sentence, ~1,500 free lookups/day, no credit card.
# "google": legacy Cloud Translation v2 fallback (needs GCP billing).
# Future paid LLM providers (Claude/GPT) slot in here the same way.
PROVIDER = os.getenv("PROVIDER", "gemini").strip().lower()

# Gemini API key — free from https://aistudio.google.com ("Get API key").
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Model behind the lookup. "-latest" alias auto-tracks Google's current
# flash-lite model, so it won't go stale the way a pinned version number
# eventually does (confirmed live against the API — see conversation).
# Override in .env if Google ever retires this alias too.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest").strip()

# Legacy: Google Cloud Translation API key (GCP console, billing required).
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()

# --- Behaviour ----------------------------------------------------------
SOURCE_LANG = "en"
# TARGET_LANGUAGE / TARGET_LANG / LANGUAGE_GLYPH come from settings.json:
refresh_language()

# Longest selection sent to the API. Caps per-lookup spend and keeps the
# popup readable; longer selections are truncated at a word boundary.
MAX_CHARS = int(os.getenv("MAX_CHARS", "500"))

POPUP_TIMEOUT_MS = int(os.getenv("POPUP_TIMEOUT_MS", "6000"))   # auto-dismiss
# Ceiling, not a delay — LLM calls need more headroom than translate v2 did.
API_TIMEOUT_S = float(os.getenv("API_TIMEOUT_S", "10"))

# Global toggle hotkey (pynput GlobalHotKeys syntax).
TOGGLE_HOTKEY = os.getenv("TOGGLE_HOTKEY", "<ctrl>+<alt>+k")

# Debounce between XButton2 triggers, so button-mashing can't queue lookups.
DEBOUNCE_S = 0.3
