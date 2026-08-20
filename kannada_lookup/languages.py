"""Curated target-language list for the first-run setup dialog.

Fields per entry:
  name  - English name; interpolated into the LLM prompt ("English-Hindi
          dictionary", "translation in Hindi", …). The prompt is the only
          thing the LLM needs, so any language Gemini knows would work -
          this list just keeps the dropdown tidy.
  code  - ISO 639-1 code; used only by the legacy Google Translate
          provider (PROVIDER=google in .env).
  glyph - one native character for the tray icon.
"""

import unicodedata

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
    {"name": "Swedish",    "code": "sv", "glyph": "Å"},
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
    edited settings.json) - falls back to a generic latin glyph."""
    entry = _BY_NAME.get(name)
    if entry:
        return entry
    return {"name": name, "code": "", "glyph": (name[:1].upper() or "?")}


# Unicode ranges a translation into this language must actually touch.
#
# Defined only where the target script differs from English's - a Latin
# target (Swedish, Spanish, German…) shares the ASCII range with the input
# word, so there is nothing a range check could prove. Absent from this
# table means "not checkable", which is treated as valid.
#
# This exists because models answer in the wrong script: asking for the
# Kannada for "suppression" returned "दमन", which is Devanagari - correct
# word, wrong alphabet, useless to a Kannada reader. It is cheap to detect
# (no model call) and the wrong script is unambiguous, unlike "is this the
# best word", which we deliberately do NOT try to judge here.
SCRIPT_RANGES = {
    "Kannada":   [(0x0C80, 0x0CFF)],
    "Hindi":     [(0x0900, 0x097F)],
    "Marathi":   [(0x0900, 0x097F)],
    "Tamil":     [(0x0B80, 0x0BFF)],
    "Telugu":    [(0x0C00, 0x0C7F)],
    "Malayalam": [(0x0D00, 0x0D7F)],
    "Bengali":   [(0x0980, 0x09FF)],
    "Gujarati":  [(0x0A80, 0x0AFF)],
    "Punjabi":   [(0x0A00, 0x0A7F)],
    "Odia":      [(0x0B00, 0x0B7F)],
    "Urdu":      [(0x0600, 0x06FF), (0x0750, 0x077F)],
    "Arabic":    [(0x0600, 0x06FF), (0x0750, 0x077F)],
    "Russian":   [(0x0400, 0x04FF)],
    "Thai":      [(0x0E00, 0x0E7F)],
    "Korean":    [(0xAC00, 0xD7AF), (0x1100, 0x11FF)],
    # Japanese mixes three scripts in ordinary text and a single word may
    # legitimately be written in any one of them, so all three count.
    "Japanese":  [(0x3040, 0x309F), (0x30A0, 0x30FF), (0x4E00, 0x9FFF)],
    "Chinese (Simplified)": [(0x4E00, 0x9FFF), (0x3400, 0x4DBF)],
}


def uses_expected_script(text: str, language: str) -> bool:
    """True when `text` contains at least one character of `language`'s
    own script AND none from any other checkable script - or when
    `language` has no checkable script (Latin targets, or a name not in
    LANGUAGES), in which case there is nothing to reject.

    "At least one", not "every character": real translations mix in
    digits, punctuation, and sometimes a Latin acronym (never flagged -
    Latin has no entry in SCRIPT_RANGES), and requiring every character
    to match would reject those valid answers.

    The "none from any OTHER script" half exists because flash-lite
    returned "कृतज्ञತೆ" for the Kannada translation of "gratitude" - four
    Devanagari characters (कृतज्ञ) followed by one real Kannada syllable
    (ತೆ). The old at-least-one rule passed it: the string does contain a
    Kannada character, just not enough of them. Checking foreign scripts
    by range membership, not a fixed set of names, means Hindi and
    Marathi (which share one Unicode block) never flag each other - the
    exclusion is by range value, not by which language name owns it.
    """
    ranges = SCRIPT_RANGES.get(language)
    if not ranges:
        return True
    own = set(ranges)
    has_own = has_foreign = False
    for c in text:
        cp = ord(c)
        if any(lo <= cp <= hi for lo, hi in own):
            has_own = True
        elif _is_foreign_letter(cp):
            has_foreign = True
    return has_own and not has_foreign


# Latin and its extensions (Basic Latin through Latin Extended-B plus IPA).
# Never counted as foreign: a translation may legitimately carry an English
# acronym or loanword, and rejecting those would fail valid answers.
_LATIN_MAX = 0x02AF


def _is_foreign_letter(cp: int) -> bool:
    """True for a LETTER from some script other than the target's.

    Checked by Unicode letter category rather than membership in
    SCRIPT_RANGES, because a fixed list only knows the scripts this app
    happens to support. flash-lite returned "θಳಿಗೆದು" for the Kannada
    translation of "fragile" - a Greek theta spliced into Kannada text.
    Greek isn't a target language here, so a list-based check treated
    that character as neither own nor foreign and passed the whole
    string. Anything the Unicode database calls a letter, that isn't
    Latin and isn't the target script, is wrong in a translation.

    Digits, punctuation, spaces and combining marks are all excluded by
    the category test, so they never trigger a false rejection.
    """
    if cp <= _LATIN_MAX:
        return False
    return unicodedata.category(chr(cp)).startswith("L")
