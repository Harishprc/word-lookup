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

from pynput.keyboard import Controller, Key

SUPPRESSES_CLICK = True

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


def send_copy():
    for mod in (Key.shift, Key.shift_r, Key.alt):
        _kbd.release(mod)
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
