"""Curated target-language list for the first-run setup dialog.

Fields per entry:
  name  — English name; interpolated into the LLM prompt ("English-Hindi
          dictionary", "translation in Hindi", …). The prompt is the only
          thing the LLM needs, so any language Gemini knows would work —
          this list just keeps the dropdown tidy.
  code  — ISO 639-1 code; used only by the legacy Google Translate
          provider (PROVIDER=google in .env).
  glyph — one native character for the tray icon.
"""

LANGUAGES = [
    # Indian languages
    {"name": "Kannada",    "code": "kn", "glyph": "ಕ"},
    {"name": "Hindi",      "code": "hi", "glyph": "अ"},
    {"name": "Tamil",      "code": "ta", "glyph": "த"},
    {"name": "Telugu",     "code": "te", "glyph": "త"},
    {"name": "Malayalam",  "code": "ml", "glyph": "മ"},
    {"name": "Marathi",    "code": "mr", "glyph": "म"},
    {"name": "Bengali",    "code": "bn", "glyph": "ব"},
    {"name": "Gujarati",   "code": "gu", "glyph": "ગ"},
    {"name": "Punjabi",    "code": "pa", "glyph": "ਪ"},
    {"name": "Odia",       "code": "or", "glyph": "ଓ"},
    {"name": "Urdu",       "code": "ur", "glyph": "ا"},
    # World languages
    {"name": "Spanish",    "code": "es", "glyph": "Ñ"},
    {"name": "French",     "code": "fr", "glyph": "Ç"},
    {"name": "German",     "code": "de", "glyph": "ß"},
    {"name": "Japanese",   "code": "ja", "glyph": "あ"},
    {"name": "Korean",     "code": "ko", "glyph": "한"},
    {"name": "Chinese (Simplified)", "code": "zh", "glyph": "中"},
    {"name": "Arabic",     "code": "ar", "glyph": "ع"},
    {"name": "Russian",    "code": "ru", "glyph": "Я"},
    {"name": "Portuguese", "code": "pt", "glyph": "Ã"},
    {"name": "Italian",    "code": "it", "glyph": "È"},
    {"name": "Turkish",    "code": "tr", "glyph": "Ş"},
    {"name": "Vietnamese", "code": "vi", "glyph": "ơ"},
    {"name": "Thai",       "code": "th", "glyph": "ท"},
    {"name": "Indonesian", "code": "id", "glyph": "ᬅ"},
]

_BY_NAME = {entry["name"]: entry for entry in LANGUAGES}

_DEFAULT = {"name": "Kannada", "code": "kn", "glyph": "ಕ"}


def get(name: str) -> dict:
    """Entry for a language name; tolerant of unknown names (e.g. a hand-
    edited settings.json) — falls back to a generic latin glyph."""
    entry = _BY_NAME.get(name)
    if entry:
        return entry
    return {"name": name, "code": "", "glyph": (name[:1].upper() or "?")}
