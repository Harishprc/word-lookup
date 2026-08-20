"""macOS backend - EXPERIMENTAL, written to documented APIs, never run on
real hardware (author has no Mac). Expect to debug before trusting.

Clipboard: pbpaste/pbcopy subprocesses - universally available, no pyobjc
dependency. Change detection is content-compare (NSPasteboard.changeCount
would be exact but needs pyobjc; content-compare is good enough because
grab_selection snapshots first and only waits for *difference*).

Hook suppression: pynput's darwin_intercept receives the Quartz event and
can swallow it by returning None. Requires the app to be granted BOTH
Accessibility and Input Monitoring permissions (System Settings →
Privacy & Security), else the listener sees nothing.

Copy chord: Cmd+C, not Ctrl+C.
"""

import subprocess

from pynput.keyboard import Controller, Key, KeyCode

SUPPRESSES_CLICK = True
SUPPRESSES_HOTKEY = True
# change_token() is a content compare here, so capture.py can't tell "the
# selection copied but happened to match what was already on the
# clipboard" apart from "nothing was selected". See capture.grab_selection.
TOKEN_IS_CONTENT = True

_kbd = Controller()


def read_text():
    try:
        out = subprocess.run(
            ["pbpaste"], capture_output=True, timeout=2
        )
        return out.stdout.decode("utf-8", errors="replace") or None
    except Exception:
        return None


def write_text(text):
    # None means the original clipboard content couldn't be read - leave
    # the clipboard alone rather than overwriting it with an empty string.
    if text is None:
        return
    try:
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), timeout=2)
    except Exception:
        pass


def change_token():
    # Content IS the token - capture.py only compares tokens for equality.
    return read_text()


def send_copy(release_vks=()):
    for mod in (Key.shift, Key.shift_r, Key.alt):
        _kbd.release(mod)
    # Keyboard-triggered lookups leave the chord's own keys held; release
    # them so Cmd+C isn't polluted. See win.send_copy for the rationale.
    #
    # `vk` is a Windows virtual-key code (hotkeys.Combo.vk) - it does NOT
    # map to a macOS keycode, so KeyCode.from_vk(vk) targets the wrong key
    # here. For letters/digits the Windows VK happens to equal the ASCII
    # code, so KeyCode.from_char() releases the right key regardless of
    # platform (pynput resolves the native keycode itself). Anything else
    # (named/punctuation keys) has no reliable translation available -
    # best-effort fall back to from_vk, same as before.
    for vk in release_vks:
        try:
            if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:  # '0'-'9', 'A'-'Z'
                _kbd.release(KeyCode.from_char(chr(vk).lower()))
            else:
                _kbd.release(KeyCode.from_vk(vk))
        except Exception:
            pass
    _kbd.press(Key.cmd)
    _kbd.press("c")
    _kbd.release("c")
    _kbd.release(Key.cmd)


def make_listener(on_down, enabled):
    """pynput mouse.Listener using darwin_intercept: return the event to
    pass it through, None to swallow it. Quartz button numbering:
    0=left 1=right 2=middle 3=Back(XButton1) 4=Forward(XButton2).

    Quartz comes from pyobjc-framework-Quartz, which pynput already
    requires on macOS - no extra dependency.
    """
    import Quartz
    from pynput import mouse

    def _intercept(event_type, event):
        if event_type not in (
            Quartz.kCGEventOtherMouseDown,
            Quartz.kCGEventOtherMouseUp,
        ):
            return event
        button = Quartz.CGEventGetIntegerValueField(
            event, Quartz.kCGMouseEventButtonNumber
        )
        if button != 4 or not enabled.is_set():
            return event
        if event_type == Quartz.kCGEventOtherMouseDown:
            on_down()
        return None  # swallow down+up - app never sees Forward

    return mouse.Listener(darwin_intercept=_intercept)


def make_key_listener(bindings):
    """Keyboard equivalent of make_listener: swallow the chord via
    darwin_intercept so the focused app never sees it. `bindings` is a
    list of (combo, on_trigger, enabled) triples - one shared event tap
    serves every bound shortcut instead of installing one per shortcut.

    pynput's macOS keyboard listener exposes the same intercept hook as
    the mouse one. Modifier state comes from the Quartz event flags rather
    than a polling call, since Quartz hands it to us directly.
    """
    import Quartz
    from pynput import keyboard

    swallowed = {}  # id(combo) -> whether its key-down is currently held

    def _flags_match(combo, flags):
        return (
            bool(flags & Quartz.kCGEventFlagMaskControl) == combo.ctrl
            and bool(flags & Quartz.kCGEventFlagMaskAlternate) == combo.alt
            and bool(flags & Quartz.kCGEventFlagMaskShift) == combo.shift
            and bool(flags & Quartz.kCGEventFlagMaskCommand) == combo.meta
        )

    def _intercept(event_type, event):
        if event_type not in (Quartz.kCGEventKeyDown, Quartz.kCGEventKeyUp):
            return event
        # macOS virtual key codes differ from Windows ones; combo.vk is a
        # Windows VK. Compare on the mapped mac keycode instead. UNTESTED
        # - no Mac to verify on.
        keycode = Quartz.CGEventGetIntegerValueField(
            event, Quartz.kCGKeyboardEventKeycode
        )
        for combo, on_trigger, enabled in bindings:
            if keycode != _mac_keycode(combo):
                continue

            if event_type == Quartz.kCGEventKeyDown:
                flags = Quartz.CGEventGetFlags(event)
                if not enabled.is_set() or not _flags_match(combo, flags):
                    continue
                if not swallowed.get(id(combo)):
                    swallowed[id(combo)] = True
                    on_trigger()
                return None
            # Match on our own bookkeeping, not on modifier state - by the
            # time the key comes up the user has often already let go of
            # Ctrl/Alt. Fall through to the next binding rather than
            # returning: two shortcuts can share a mac keycode with
            # different modifiers (Ctrl+G and Ctrl+Alt+G are both 0x05), and
            # returning here would skip the binding that actually swallowed
            # the key-down - leaving its `swallowed` flag stuck True, so it
            # never fires again. Same shape as win.py's WM_KEYUP branch.
            if swallowed.get(id(combo)):
                swallowed[id(combo)] = False
                return None
        return event

    return keyboard.Listener(darwin_intercept=_intercept)


# hotkeys.Combo.key (display name, matched here upper-cased) -> macOS
# virtual keycode (kVK_* constants from Carbon/HIToolbox Events.h). Covers
# every key hotkeys.parse() can produce a Combo for, aliases included, so a
# shortcut valid on Windows/Linux also has a real trigger on macOS. Ins/
# Insert has no reliable mac equivalent and is left unmapped; anything
# absent falls through as -1 (never matches), which degrades to "no
# keyboard trigger on this Mac" rather than misfiring on the wrong key.
_MAC_KEYCODES = {
    "A": 0x00, "S": 0x01, "D": 0x02, "F": 0x03, "H": 0x04, "G": 0x05,
    "Z": 0x06, "X": 0x07, "C": 0x08, "V": 0x09, "B": 0x0B, "Q": 0x0C,
    "W": 0x0D, "E": 0x0E, "R": 0x0F, "Y": 0x10, "T": 0x11, "O": 0x1F,
    "U": 0x20, "I": 0x22, "P": 0x23, "L": 0x25, "J": 0x26, "K": 0x28,
    "N": 0x2D, "M": 0x2E,
    "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15, "5": 0x17, "6": 0x16,
    "7": 0x1A, "8": 0x1C, "9": 0x19, "0": 0x1D,
    "SPACE": 0x31, "TAB": 0x30, "RETURN": 0x24, "ENTER": 0x24,
    "BACKSPACE": 0x33, "DEL": 0x75, "DELETE": 0x75,
    "HOME": 0x73, "END": 0x77, "PGUP": 0x74, "PAGEUP": 0x74,
    "PGDOWN": 0x79, "PAGEDOWN": 0x79, "ESC": 0x35, "ESCAPE": 0x35,
    "LEFT": 0x7B, "RIGHT": 0x7C, "DOWN": 0x7D, "UP": 0x7E,
    "`": 0x32, "-": 0x1B, "=": 0x18, "[": 0x21, "]": 0x1E, "\\": 0x2A,
    ";": 0x29, "'": 0x27, ",": 0x2B, ".": 0x2F, "/": 0x2C,
    "F1": 0x7A, "F2": 0x78, "F3": 0x63, "F4": 0x76, "F5": 0x60,
    "F6": 0x61, "F7": 0x62, "F8": 0x64, "F9": 0x65, "F10": 0x6D,
    "F11": 0x67, "F12": 0x6F, "F13": 0x69, "F14": 0x6B, "F15": 0x71,
    "F16": 0x6A, "F17": 0x40, "F18": 0x4F, "F19": 0x50, "F20": 0x5A,
}


def _mac_keycode(combo):
    return _MAC_KEYCODES.get(combo.key.upper(), -1)
