"""macOS backend — EXPERIMENTAL, written to documented APIs, never run on
real hardware (author has no Mac). Expect to debug before trusting.

Clipboard: pbpaste/pbcopy subprocesses — universally available, no pyobjc
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
    try:
        subprocess.run(["pbcopy"], input=(text or "").encode("utf-8"), timeout=2)
    except Exception:
        pass


def change_token():
    # Content IS the token — capture.py only compares tokens for equality.
    return read_text()


def send_copy(release_vks=()):
    for mod in (Key.shift, Key.shift_r, Key.alt):
        _kbd.release(mod)
    # Keyboard-triggered lookups leave the chord's own keys held; release
    # them so Cmd+C isn't polluted. See win.send_copy for the rationale.
    for vk in release_vks:
        try:
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
    requires on macOS — no extra dependency.
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
        return None  # swallow down+up — app never sees Forward

    return mouse.Listener(darwin_intercept=_intercept)


def make_key_listener(combo, on_trigger, enabled):
    """Keyboard equivalent of make_listener: swallow the chord via
    darwin_intercept so the focused app never sees it.

    pynput's macOS keyboard listener exposes the same intercept hook as
    the mouse one. Modifier state comes from the Quartz event flags rather
    than a polling call, since Quartz hands it to us directly.
    """
    import Quartz
    from pynput import keyboard

    swallowed = {"down": False}

    def _flags_match(flags):
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
        # Windows VK. Compare on the produced character instead, which is
        # stable across both. UNTESTED — no Mac to verify on.
        keycode = Quartz.CGEventGetIntegerValueField(
            event, Quartz.kCGKeyboardEventKeycode
        )
        if keycode != _mac_keycode(combo):
            return event

        if event_type == Quartz.kCGEventKeyDown:
            flags = Quartz.CGEventGetFlags(event)
            if not enabled.is_set() or not _flags_match(flags):
                return event
            if not swallowed["down"]:
                swallowed["down"] = True
                on_trigger()
            return None
        if swallowed["down"]:
            swallowed["down"] = False
            return None
        return event

    return keyboard.Listener(darwin_intercept=_intercept)


# Windows VK -> macOS virtual keycode, letters and digits only. Anything
# else falls through as -1 (never matches), which degrades to "no keyboard
# trigger on this Mac" rather than misfiring on the wrong key.
_MAC_KEYCODES = {
    "A": 0x00, "S": 0x01, "D": 0x02, "F": 0x03, "H": 0x04, "G": 0x05,
    "Z": 0x06, "X": 0x07, "C": 0x08, "V": 0x09, "B": 0x0B, "Q": 0x0C,
    "W": 0x0D, "E": 0x0E, "R": 0x0F, "Y": 0x10, "T": 0x11, "O": 0x1F,
    "U": 0x20, "I": 0x22, "P": 0x23, "L": 0x25, "J": 0x26, "K": 0x28,
    "N": 0x2D, "M": 0x2E,
    "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15, "5": 0x17, "6": 0x16,
    "7": 0x1A, "8": 0x1C, "9": 0x19, "0": 0x1D,
}


def _mac_keycode(combo):
    return _MAC_KEYCODES.get(combo.key.upper(), -1)
