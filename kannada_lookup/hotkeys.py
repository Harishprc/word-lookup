"""Shortcut strings: parse, normalise, and flag the dangerous ones.

Shortcuts are stored the way Qt writes them — "Ctrl+Alt+G" — because the
recorder in setup_dialog.py is a QKeySequenceEdit and that is its native
portable format. This module turns that string into something the OS hook
can match against, and warns about bindings that would hurt.

Deliberately free of Qt, pynput and win32 imports: this is the one piece
of the hotkey feature that unit tests can exercise without a display, a
keyboard hook, or Windows.
"""

from typing import NamedTuple

# --- Virtual-key codes (winuser.h) --------------------------------------
# Letters and digits map to their ASCII code, which is why they need no
# table. Everything else does.
_NAMED_VKS = {
    "SPACE": 0x20, "TAB": 0x09, "RETURN": 0x0D, "ENTER": 0x0D,
    "BACKSPACE": 0x08, "DEL": 0x2E, "DELETE": 0x2E, "INS": 0x2D,
    "INSERT": 0x2D, "HOME": 0x24, "END": 0x23, "PGUP": 0x21,
    "PAGEUP": 0x21, "PGDOWN": 0x22, "PAGEDOWN": 0x22, "ESC": 0x1B,
    "ESCAPE": 0x1B, "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
    "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC,
    ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
}
_NAMED_VKS.update({f"F{n}": 0x6F + n for n in range(1, 25)})  # VK_F1 = 0x70

_MODIFIER_NAMES = {"CTRL", "CONTROL", "ALT", "SHIFT", "META", "WIN"}


class Combo(NamedTuple):
    """A parsed shortcut. `vk` is the Windows virtual-key code of the
    non-modifier key; the booleans are which modifiers must be held."""

    ctrl: bool
    alt: bool
    shift: bool
    meta: bool
    key: str          # display name of the non-modifier key, e.g. "G"
    vk: int

    def text(self) -> str:
        """Back to Qt portable form. Order matches QKeySequence's own."""
        parts = []
        if self.ctrl:
            parts.append("Ctrl")
        if self.alt:
            parts.append("Alt")
        if self.shift:
            parts.append("Shift")
        if self.meta:
            parts.append("Meta")
        parts.append(self.key)
        return "+".join(parts)

    def pynput_text(self) -> str:
        """pynput GlobalHotKeys syntax, e.g. "<ctrl>+<alt>+g".

        Only the Linux backend needs this — it cannot suppress on X11 and
        so falls back to GlobalHotKeys instead of a filtering hook.
        """
        parts = []
        if self.ctrl:
            parts.append("<ctrl>")
        if self.alt:
            parts.append("<alt>")
        if self.shift:
            parts.append("<shift>")
        if self.meta:
            parts.append("<cmd>")
        key = self.key
        parts.append(key.lower() if len(key) == 1 else f"<{key.lower()}>")
        return "+".join(parts)


def parse(text: str) -> Combo | None:
    """Parse "Ctrl+Alt+G" into a Combo, or None if it isn't usable.

    Rejects: empty input, modifier-only chords (no key to trigger on), and
    keys we have no virtual-key code for. Returning None rather than
    raising keeps callers simple — an unusable stored shortcut just means
    "no keyboard trigger", never a crash on startup.
    """
    if not text or not text.strip():
        return None

    # "+" as the key ("Ctrl++") splits badly on "+", so peel it off first.
    raw = text.strip()
    if raw.endswith("++"):
        key_token = "+"
        head = raw[:-2]
        tokens = head.split("+") if head else []
    else:
        tokens = raw.split("+")
        key_token = tokens.pop()

    ctrl = alt = shift = meta = False
    for tok in tokens:
        name = tok.strip().upper()
        if name in ("CTRL", "CONTROL"):
            ctrl = True
        elif name == "ALT":
            alt = True
        elif name == "SHIFT":
            shift = True
        elif name in ("META", "WIN"):
            meta = True
        else:
            return None  # unknown modifier — refuse rather than guess

    key = key_token.strip()
    if not key or key.upper() in _MODIFIER_NAMES:
        return None  # modifier-only chord can never fire

    vk = _vk_for(key)
    if vk is None:
        return None

    return Combo(ctrl, alt, shift, meta, _display(key), vk)


def _vk_for(key: str) -> int | None:
    upper = key.upper()
    if len(upper) == 1 and (upper.isalpha() or upper.isdigit()):
        return ord(upper)
    if upper == "+":
        return 0xBB  # VK_OEM_PLUS
    return _NAMED_VKS.get(upper)


def _display(key: str) -> str:
    upper = key.upper()
    is_fkey = upper.startswith("F") and upper[1:].isdigit()
    if len(upper) == 1 or is_fkey:
        return upper
    return key.strip().title()


def from_pynput(text: str) -> str:
    """Convert pynput's GlobalHotKeys syntax to Qt's portable form.

    v0.1.0 stored TOGGLE_HOTKEY in .env as "<ctrl>+<alt>+k". Anyone
    upgrading still has that in their .env, so it has to keep working.
    """
    if not text:
        return ""
    if "<" not in text:
        return normalize(text)  # already Qt-style
    parts = [p.strip().strip("<>") for p in text.split("+")]
    return normalize("+".join(p for p in parts if p))


def normalize(text: str) -> str:
    """Canonical form, or "" if unparseable. Used before saving so the
    stored value and the matched value can never drift apart."""
    combo = parse(text)
    return combo.text() if combo else ""


# --- Risk warnings -------------------------------------------------------
# Warn, never block: the user knows their own machine. Each message names
# the actual consequence, because "this shortcut is risky" tells them
# nothing they can act on.

_RISKY_EXACT = {
    "Ctrl+C": "Ctrl+C is Copy — binding it would break copying everywhere.",
    "Ctrl+V": "Ctrl+V is Paste — binding it would break pasting everywhere.",
    "Ctrl+X": "Ctrl+X is Cut — binding it would break cutting everywhere.",
    "Ctrl+Z": "Ctrl+Z is Undo in nearly every app.",
    "Ctrl+Y": "Ctrl+Y is Redo in nearly every app.",
    "Ctrl+A": "Ctrl+A is Select All in nearly every app.",
    "Ctrl+S": "Ctrl+S is Save — you would stop being able to save files.",
    "Ctrl+W": "Ctrl+W closes the current tab or document in most apps.",
    "Ctrl+Q": "Ctrl+Q quits the app outright in Firefox, Slack and others.",
    "Ctrl+N": "Ctrl+N opens a new window or document in most apps.",
    "Ctrl+T": "Ctrl+T opens a new tab in every browser.",
    "Ctrl+P": "Ctrl+P opens the print dialog in most apps.",
    "Ctrl+F": "Ctrl+F opens Find in most apps.",
    "Alt+F4": "Alt+F4 closes the active window — Windows handles it before "
              "any app sees it, so it cannot be intercepted.",
    "Alt+Tab": "Alt+Tab switches windows and is reserved by Windows.",
    "Ctrl+Alt+Del": "Ctrl+Alt+Del is reserved by Windows and cannot be "
                    "intercepted by any program.",
}

# Known collisions in apps this tool is explicitly used inside.
_RISKY_APP = {
    "Ctrl+Alt+D": "Ctrl+Alt+D inserts an endnote in Microsoft Word.",
    "Ctrl+Alt+F": "Ctrl+Alt+F inserts a footnote in Microsoft Word.",
    "Ctrl+Alt+K": "Ctrl+Alt+K runs AutoFormat in Microsoft Word.",
    "Ctrl+Alt+M": "Ctrl+Alt+M inserts a comment in Microsoft Word.",
}


def risk_warning(text: str, suppressed: bool = True) -> str | None:
    """Human-readable reason this shortcut is a bad idea, or None.

    Where the hook swallows the chord (`suppressed=True`), an app collision
    is mostly theoretical. Where it doesn't — X11 can't intercept at all,
    and suppression can be missed during a focus change even where it's
    normally supported — the chord also reaches the app, so the warning
    says that instead of offering false reassurance.
    """
    combo = parse(text)
    if combo is None:
        return None
    canonical = combo.text()

    if canonical in _RISKY_EXACT:
        return _RISKY_EXACT[canonical]
    if canonical in _RISKY_APP:
        if suppressed:
            return _RISKY_APP[canonical] + " Word Lookup swallows the key " \
                                           "here, so this is usually safe."
        return _RISKY_APP[canonical] + " This shortcut is NOT swallowed on " \
                                       "this system, so it will also reach " \
                                       "that app."
    if combo.meta:
        return ("Windows reserves most Win-key shortcuts and handles them "
                "before any program sees them.")
    if not (combo.ctrl or combo.alt or combo.meta):
        return ("A shortcut with no Ctrl or Alt will fire while you are "
                "typing normally.")
    return None
