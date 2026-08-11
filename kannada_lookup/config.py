"""Configuration: .env for secrets, data/settings.json for user choices.

.env (copy .env.example, or let the first-run dialog create it) holds the
API key — never hardcoded, never committed. settings.json holds the
one-time setup answers (target language); its absence IS the first-run
signal.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from . import hotkeys, languages


def _app_root() -> Path:
    """Where writable user data lives.

    Source checkout: the project root (one level above this package), as
    it has always been — .env and data/ sit next to the code.

    Frozen .exe (PyInstaller onefile): __file__ points inside the temp
    _MEIxxxx extraction dir, which is DELETED on exit — writing there
    would lose the key, language and register on every quit. So the
    frozen build writes to %LOCALAPPDATA%\\WordLookup instead.
    """
    if getattr(sys, "frozen", False):
        base = Path(os.getenv("LOCALAPPDATA") or Path.home()) / "WordLookup"
        base.mkdir(parents=True, exist_ok=True)
        return base
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _app_root()
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


def update_settings(**fields) -> None:
    """Merge fields into settings.json, preserving keys we didn't touch.

    Merge rather than overwrite: settings.json now holds the shortcuts as
    well as the language, and a plain write of one field would silently
    erase the others the next time the setup dialog ran.

    Passing None for a field leaves it alone; pass "" to clear one.
    """
    current = load_settings() or {}
    current.update({k: v for k, v in fields.items() if v is not None})
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
    refresh_language()
    refresh_hotkeys()


def save_settings(target_language: str) -> None:
    """First-run/language-change entry point. Kept as its own name because
    the setup dialog and tests both call it."""
    update_settings(target_language=target_language)


def save_api_key(key: str) -> None:
    """Write the Gemini key into .env (create or append). Called by the
    first-run dialog so cloned installs need zero manual file editing."""
    lines = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
        lines = [
            l for l in lines
            if not l.startswith("GEMINI_API_KEY=") and not l.startswith("PROVIDER=")
        ]
    lines += [f"GEMINI_API_KEY={key.strip()}", "PROVIDER=gemini"]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
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
    # Legacy Google-provider ISO code. No fallback to "kn": GeminiProvider
    # reads TARGET_LANGUAGE (the free-text name) instead of this, so
    # defaulting an unrecognized name here would silently translate into
    # Kannada under PROVIDER=google while Gemini honors the real name.
    # Left blank, GoogleTranslateProvider fails loudly with an API error
    # instead of translating into the wrong language.
    TARGET_LANG = entry["code"]
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
# model, so it won't go stale the way a pinned version number eventually
# does. Override in .env if Google ever retires this alias too.
#
# flash, not flash-lite: flash-lite is cheaper and has a higher daily
# quota, but it invents plausible-looking words in low-resource scripts —
# "restricted" came back as "ಮಿಚ್ಛಿತ / ನಿಯನ್ಶ್ರಿತ" in Kannada, neither a real
# word. Set GEMINI_MODEL=gemini-flash-lite-latest to trade that accuracy
# back for quota if you look up hundreds of words a day.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest").strip()

# Legacy: Google Cloud Translation API key (GCP console, billing required).
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()

# --- Sync (optional) ------------------------------------------------------
# GitHub personal access token, "gist" scope only — shares the lookup
# cache with the Android app via one private Gist. See sync.py. Unset =
# sync simply never runs; nothing else about the app changes.
GITHUB_PAT = os.getenv("GITHUB_PAT", "").strip()

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

# --- Shortcuts ----------------------------------------------------------
# Stored in settings.json in Qt portable form ("Ctrl+Alt+G") because the
# recorder in the setup dialog is a QKeySequenceEdit. settings.json wins;
# the .env vars are the fallback so v0.1.0 installs keep working.
#
# LOOKUP_HOTKEY is empty by default: the mouse Forward button remains the
# primary trigger, and nothing about an existing install changes until the
# user records a shortcut. It exists for laptops with no side buttons.

def refresh_hotkeys() -> None:
    """Re-read shortcuts after the recorder saves them."""
    global LOOKUP_HOTKEY, TOGGLE_HOTKEY
    settings = load_settings() or {}

    stored = settings.get("lookup_hotkey")
    if stored is None:
        stored = os.getenv("LOOKUP_HOTKEY", "")
    LOOKUP_HOTKEY = hotkeys.from_pynput(stored)

    stored = settings.get("toggle_hotkey")
    if stored is None:
        stored = os.getenv("TOGGLE_HOTKEY", "<ctrl>+<alt>+k")
    TOGGLE_HOTKEY = hotkeys.from_pynput(stored)


refresh_hotkeys()

# Debounce between XButton2 triggers, so button-mashing can't queue lookups.
DEBOUNCE_S = 0.3
