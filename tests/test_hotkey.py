"""Tests for the keyboard-shortcut layer.

Everything here is deliberately free of Qt, pynput and win32: the parsing,
validation and persistence can all be exercised without a display or an
installed hook. The one thing that genuinely cannot be unit-tested is
whether the OS hook actually swallows the chord — that needs a real
keypress in a real app (see README / the Word check).
"""

import pytest

from kannada_lookup import hotkeys


# --- parsing ------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected_vk",
    [
        ("Ctrl+Alt+G", 0x47),
        ("ctrl+alt+g", 0x47),        # case-insensitive
        ("Ctrl+Shift+F5", 0x74),     # F-keys
        ("Alt+Space", 0x20),         # named key
        ("Ctrl+9", 0x39),            # digit
        ("Ctrl+;", 0xBA),            # punctuation
        ("Ctrl++", 0xBB),            # "+" as the key, despite being the separator
        ("Ctrl+Alt+Home", 0x24),
    ],
)
def test_parse_resolves_virtual_key(text, expected_vk):
    combo = hotkeys.parse(text)
    assert combo is not None
    assert combo.vk == expected_vk


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "Ctrl",              # modifier-only: nothing to trigger on
        "Ctrl+Shift",
        "Ctrl+Alt+Zz",       # not a real key
        "Hyper+G",           # unknown modifier — refuse rather than guess
    ],
)
def test_parse_rejects_unusable(text):
    assert hotkeys.parse(text) is None
    assert hotkeys.normalize(text) == ""


def test_parse_records_modifiers():
    combo = hotkeys.parse("Ctrl+Alt+Shift+Meta+G")
    assert (combo.ctrl, combo.alt, combo.shift, combo.meta) == (True, True, True, True)

    combo = hotkeys.parse("Alt+G")
    assert (combo.ctrl, combo.alt, combo.shift, combo.meta) == (False, True, False, False)


# --- normalisation ------------------------------------------------------


@pytest.mark.parametrize(
    "messy, canonical",
    [
        ("ctrl+alt+g", "Ctrl+Alt+G"),
        ("ALT+CTRL+G", "Ctrl+Alt+G"),        # modifier order is normalised
        ("  Ctrl+Alt+G  ", "Ctrl+Alt+G"),
        ("shift+ctrl+f1", "Ctrl+Shift+F1"),
    ],
)
def test_normalize_is_canonical(messy, canonical):
    assert hotkeys.normalize(messy) == canonical


def test_normalize_is_idempotent():
    once = hotkeys.normalize("alt+ctrl+g")
    assert hotkeys.normalize(once) == once


def test_text_round_trips_through_parse():
    for text in ("Ctrl+Alt+G", "Ctrl+Shift+F5", "Alt+Space", "Meta+G"):
        assert hotkeys.parse(text).text() == text


# --- pynput interop -----------------------------------------------------


def test_pynput_text_for_linux_backend():
    # Linux can't suppress, so it falls back to GlobalHotKeys, which needs
    # this syntax.
    assert hotkeys.parse("Ctrl+Alt+G").pynput_text() == "<ctrl>+<alt>+g"
    assert hotkeys.parse("Ctrl+Shift+F5").pynput_text() == "<ctrl>+<shift>+<f5>"


def test_from_pynput_upgrades_v010_env_values():
    # v0.1.0 stored TOGGLE_HOTKEY as "<ctrl>+<alt>+k" in .env; anyone
    # upgrading still has that, so it has to keep working.
    assert hotkeys.from_pynput("<ctrl>+<alt>+k") == "Ctrl+Alt+K"
    assert hotkeys.from_pynput("Ctrl+Alt+K") == "Ctrl+Alt+K"  # already Qt-style
    assert hotkeys.from_pynput("") == ""


# --- risk warnings ------------------------------------------------------


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("Ctrl+C", "Copy"),
        ("Ctrl+V", "Paste"),
        ("Ctrl+W", "closes"),
        ("Ctrl+Q", "quits"),
        ("Alt+F4", "closes the active window"),
        ("Ctrl+Alt+D", "endnote"),        # Word collision
        ("Ctrl+Alt+K", "AutoFormat"),     # Word collision — the v0.1.0 default
        ("Meta+G", "Windows reserves"),
        ("G", "typing normally"),         # no modifier at all
    ],
)
def test_risk_warning_names_the_consequence(text, fragment):
    warning = hotkeys.risk_warning(text)
    assert warning is not None
    assert fragment in warning


@pytest.mark.parametrize("text", ["Ctrl+Alt+G", "Ctrl+Shift+F5", "Ctrl+Alt+J"])
def test_risk_warning_silent_for_safe_combos(text):
    assert hotkeys.risk_warning(text) is None


def test_risk_warning_ignores_unparseable():
    assert hotkeys.risk_warning("") is None
    assert hotkeys.risk_warning("Ctrl") is None


# --- settings persistence -----------------------------------------------


def test_update_settings_preserves_other_keys(monkeypatch, tmp_path):
    """The bug this guards: save_settings used to write a dict containing
    only target_language, silently erasing a saved shortcut whenever the
    user changed language."""
    from kannada_lookup import config

    monkeypatch.setattr(config, "SETTINGS_PATH", tmp_path / "settings.json")
    try:
        config.save_settings("Hindi")
        config.update_settings(lookup_hotkey="Ctrl+Alt+G")
        assert config.load_settings() == {
            "target_language": "Hindi",
            "lookup_hotkey": "Ctrl+Alt+G",
        }

        config.save_settings("Tamil")  # would have wiped the shortcut before
        settings = config.load_settings()
        assert settings["lookup_hotkey"] == "Ctrl+Alt+G"
        assert settings["target_language"] == "Tamil"
    finally:
        monkeypatch.undo()
        config.refresh_language()
        config.refresh_hotkeys()


def test_update_settings_none_leaves_field_alone(monkeypatch, tmp_path):
    from kannada_lookup import config

    monkeypatch.setattr(config, "SETTINGS_PATH", tmp_path / "settings.json")
    try:
        config.update_settings(lookup_hotkey="Ctrl+Alt+G")
        config.update_settings(lookup_hotkey=None, target_language="Hindi")
        assert config.load_settings()["lookup_hotkey"] == "Ctrl+Alt+G"

        config.update_settings(lookup_hotkey="")  # explicit clear
        assert config.load_settings()["lookup_hotkey"] == ""
    finally:
        monkeypatch.undo()
        config.refresh_language()
        config.refresh_hotkeys()


def test_lookup_hotkey_defaults_to_empty(monkeypatch, tmp_path):
    """An existing install must keep working as mouse-only until the user
    opts in — no shortcut appears out of nowhere on upgrade."""
    from kannada_lookup import config

    monkeypatch.setattr(config, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.delenv("LOOKUP_HOTKEY", raising=False)
    try:
        config.save_settings("Kannada")  # a v0.1.0-shaped settings file
        config.refresh_hotkeys()
        assert config.LOOKUP_HOTKEY == ""
        assert config.TOGGLE_HOTKEY == "Ctrl+Alt+K"  # legacy default survives
    finally:
        monkeypatch.undo()
        config.refresh_language()
        config.refresh_hotkeys()
