"""Windows backend — the only one tested on real hardware.

Clipboard: pywin32. Change detection uses GetClipboardSequenceNumber, a
global counter Windows bumps on every clipboard write — exact and cheap,
no content polling needed.

Hook suppression: pynput's win32_event_filter lets us see the raw
WM_XBUTTON* message before Windows delivers it to the foreground app and
swallow it there (listener.suppress_event()).
"""

import time

import win32clipboard
from pynput.keyboard import Controller, Key

SUPPRESSES_CLICK = True

_kbd = Controller()


def _open_clipboard_retry(attempts=10):
    """OpenClipboard fails if another process holds it; retry briefly."""
    for _ in range(attempts):
        try:
            win32clipboard.OpenClipboard()
            return True
        except Exception:
            time.sleep(0.02)
    return False


def read_text():
    if not _open_clipboard_retry():
        return None
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
            return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        return None
    finally:
        win32clipboard.CloseClipboard()


def write_text(text):
    if not _open_clipboard_retry():
        return
    try:
        win32clipboard.EmptyClipboard()
        if text:
            win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


def change_token():
    return win32clipboard.GetClipboardSequenceNumber()


def send_copy():
    # Neutralise modifiers the user may be physically holding (Shift+select
    # is common; Ctrl+Shift+C would open devtools in a browser). Synthetic
    # key-ups are harmless if the key isn't held.
    for mod in (Key.shift, Key.shift_r, Key.alt):
        _kbd.release(mod)
    _kbd.press(Key.ctrl)
    _kbd.press("c")
    _kbd.release("c")
    _kbd.release(Key.ctrl)


def make_listener(on_down, enabled):
    """pynput mouse.Listener that fires on_down() on XButton2-press and
    swallows both down+up so the app underneath never sees "Forward".

    Raw Windows message constants (winuser.h):
      WM_XBUTTONDOWN 0x020B, WM_XBUTTONUP 0x020C
      HIWORD(mouseData): 1 = XButton1 (Back), 2 = XButton2 (Forward)
    """
    from pynput import mouse

    WM_XBUTTONDOWN, WM_XBUTTONUP = 0x020B, 0x020C
    listener = None  # bound below; filter only runs after start()

    def _filter(msg, data):
        if msg not in (WM_XBUTTONDOWN, WM_XBUTTONUP):
            return True  # not a side button — let it through
        if (data.mouseData >> 16) != 2:
            return True  # XButton1 (Back) stays untouched
        if not enabled.is_set():
            return True  # tool OFF — Forward works normally
        if msg == WM_XBUTTONDOWN:
            # Callback BEFORE suppress_event: suppress_event raises
            # internally to abort processing of this event, so no code
            # after it would run. Callback must be non-blocking.
            on_down()
        listener.suppress_event()

    listener = mouse.Listener(win32_event_filter=_filter)
    return listener
