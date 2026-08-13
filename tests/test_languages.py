"""Unit tests for the target-language table.

The entries feed three things: the setup dialog's dropdown, the tray icon
glyph, and the language name interpolated into the Gemini prompt. A
malformed entry breaks one of those at runtime rather than at import, so
the shape is pinned here.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kannada_lookup import languages  # noqa: E402


def test_every_entry_has_the_three_required_fields():
    for entry in languages.LANGUAGES:
        assert set(entry) == {"name", "code", "glyph"}, entry
        assert entry["name"].strip(), entry
        assert entry["code"].strip(), entry


def test_glyphs_are_a_single_character():
    """The tray icon draws this with one centred drawText call — a
    multi-character string would overflow the 64px circle."""
    for entry in languages.LANGUAGES:
        assert len(entry["glyph"]) == 1, entry


def test_no_duplicate_names_or_codes():
    names = [e["name"] for e in languages.LANGUAGES]
    codes = [e["code"] for e in languages.LANGUAGES]
    assert len(names) == len(set(names))
    assert len(codes) == len(set(codes))


def test_lookup_by_name():
    entry = languages.get("Swedish")
    assert entry["code"] == "sv"
    assert entry["glyph"] == "Å"  # Å


def test_kannada_remains_the_default():
    """settings.json absent, or naming a language not in the table, must
    still yield a usable entry — config.refresh_language() reads these
    fields unconditionally."""
    assert languages.get("Kannada")["code"] == "kn"


def test_unknown_language_degrades_instead_of_raising():
    """A hand-edited settings.json shouldn't crash startup. Note the empty
    code: config.py deliberately does NOT fall back to "kn" there, so the
    legacy Google provider fails loudly rather than silently translating
    into the wrong language."""
    entry = languages.get("Klingon")
    assert entry["name"] == "Klingon"
    assert entry["code"] == ""
    assert entry["glyph"] == "K"


def test_unknown_empty_name_still_returns_a_glyph():
    assert languages.get("")["glyph"] == "?"


# --- script validation ------------------------------------------------------


def test_correct_script_accepted():
    assert languages.uses_expected_script("ದಮನ", "Kannada")
    assert languages.uses_expected_script("दमन", "Hindi")
    assert languages.uses_expected_script("сдерживание", "Russian")


def test_wrong_script_rejected():
    """The bug this exists for: correct word, wrong alphabet. "दमन" is
    Devanagari and unreadable to a Kannada reader."""
    assert not languages.uses_expected_script("दमन", "Kannada")
    assert not languages.uses_expected_script("ದಮನ", "Hindi")
    assert not languages.uses_expected_script("suppression", "Kannada")


def test_mixed_script_rejected_even_with_one_correct_character():
    """flash-lite returned "कृतज्ञತೆ" for the Kannada translation of
    "gratitude": four Devanagari characters (कृतज्ञ) followed by one real
    Kannada syllable (ತೆ). An earlier version of this check only required
    at least one character in the target script and passed it — this
    pins the fix: at least one own-script character AND zero foreign."""
    assert not languages.uses_expected_script("कृतज्ञತೆ", "Kannada")
    # Same shape the other direction: real Devanagari (own, for Hindi)
    # plus one stray Kannada character (foreign) must still be rejected.
    assert not languages.uses_expected_script("दमಕ", "Hindi")


def test_letter_from_an_unsupported_script_is_still_rejected():
    """flash-lite returned "θಳಿಗೆದು" for the Kannada translation of
    "fragile" — a Greek theta spliced into Kannada text. Greek isn't a
    target language here, so a check that only knew about SCRIPT_RANGES
    treated that character as neither own nor foreign and passed the
    whole string. Foreign-ness is decided by Unicode letter category
    instead, so any script counts, supported or not."""
    assert not languages.uses_expected_script("θಳಿಗೆದು", "Kannada")
    assert not languages.uses_expected_script("Ωಮನ", "Kannada")  # Greek omega
    assert not languages.uses_expected_script("אಮನ", "Kannada")  # Hebrew


def test_digits_punctuation_and_spaces_never_count_as_foreign():
    """Only letters are checked — a real translation carries spaces,
    a full stop, digits, and combining marks, and rejecting any of those
    would fail valid answers."""
    assert languages.uses_expected_script("ಅವಳಿಗೆ ಶಾಶ್ವತ ಕೆಲಸ ಸಿಕ್ಕಿದೆ.", "Kannada")
    assert languages.uses_expected_script("ದಮನ (suppression), 2024", "Kannada")


def test_hindi_and_marathi_never_flag_each_other():
    """They share one Unicode block, so neither is "foreign" to the
    other — the exclusion in uses_expected_script is by range VALUE, not
    by which language name happens to own it."""
    devanagari = "कृतज्ञता"
    assert languages.uses_expected_script(devanagari, "Hindi")
    assert languages.uses_expected_script(devanagari, "Marathi")


def test_latin_targets_are_not_checked():
    """Swedish shares the ASCII range with English, so a range check can
    prove nothing — it must not reject valid answers."""
    assert languages.uses_expected_script("svar", "Swedish")
    assert languages.uses_expected_script("respuesta", "Spanish")


def test_unknown_language_is_not_checked():
    """A hand-edited settings.json naming something not in the table must
    not make every lookup fail."""
    assert languages.uses_expected_script("whatever", "Klingon")


def test_mixed_content_accepted():
    """Real translations carry digits, punctuation, and sometimes a Latin
    acronym — requiring every character to be in-script would reject them."""
    assert languages.uses_expected_script("ದಮನ (suppression), 2024", "Kannada")


def test_japanese_accepts_any_of_its_three_scripts():
    assert languages.uses_expected_script("ひらがな", "Japanese")   # hiragana
    assert languages.uses_expected_script("カタカナ", "Japanese")   # katakana
    assert languages.uses_expected_script("漢字", "Japanese")      # kanji


def test_every_script_range_language_exists_in_the_table():
    """Guards against a typo in SCRIPT_RANGES silently disabling the check
    for a language — a key that matches no entry would never be consulted."""
    names = {e["name"] for e in languages.LANGUAGES}
    for name in languages.SCRIPT_RANGES:
        assert name in names, f"SCRIPT_RANGES key not a known language: {name}"


def test_every_language_glyph_matches_its_own_script_range():
    """Cross-check the two independent tables: a language's tray glyph is a
    native character, so it must satisfy that language's own range."""
    for entry in languages.LANGUAGES:
        if entry["name"] in languages.SCRIPT_RANGES:
            assert languages.uses_expected_script(
                entry["glyph"], entry["name"]
            ), entry
