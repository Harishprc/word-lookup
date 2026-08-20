"""Windows backend - the only one tested on real hardware.

Clipboard: pywin32. Change detection uses GetClipboardSequenceNumber, a
global counter Windows bumps on every clipboard write - exact and cheap,
no content polling needed.

Hook suppression: pynput's win32_event_filter lets us see the raw
WM_XBUTTON* message before Windows delivers it to the foreground app and
swallow it there (listener.suppress_event()).
"""

import time

import win32api
import win32clipboard
from pynput.keyboard import Controller, Key, KeyCode

SUPPRESSES_CLICK = True
SUPPRESSES_HOTKEY = True
# change_token() is an exact sequence number here - it always moves on a
# write, content-identical or not. See mac.py/linux.py for the opposite.
TOKEN_IS_CONTENT = False

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
    # None means the original clipboard content couldn't be read (open
    # failed or held nothing we understand) - leave the clipboard alone
    # rather than emptying it out from under the user.
    if text is None:
        return
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


def send_copy(release_vks=()):
    # Neutralise modifiers the user may be physically holding (Shift+select
    # is common; Ctrl+Shift+C would open devtools in a browser). Synthetic
    # key-ups are harmless if the key isn't held.
    for mod in (Key.shift, Key.shift_r, Key.alt, Key.alt_r):
        _kbd.release(mod)

    # When the trigger was a keyboard shortcut, its own keys are still
    # physically down - sending Ctrl+C on top of a held "G" makes the app
    # see Ctrl+G. Release them first. Callers on the mouse path pass
    # nothing and this loop is a no-op.
    for vk in release_vks:
        try:
            _kbd.release(KeyCode.from_vk(vk))
        except Exception:
            pass  # unmappable vk - the Ctrl+C below is still worth trying

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
            return True  # not a side button - let it through
        if (data.mouseData >> 16) != 2:
            return True  # XButton1 (Back) stays untouched
        if not enabled.is_set():
            return True  # tool OFF - Forward works normally
        if msg == WM_XBUTTONDOWN:
            # Callback BEFORE suppress_event: suppress_event raises
            # internally to abort processing of this event, so no code
            # after it would run. Callback must be non-blocking.
            on_down()
        listener.suppress_event()

    listener = mouse.Listener(win32_event_filter=_filter)
    return listener


def make_key_listener(bindings):
    """pynput keyboard.Listener that fires on_trigger() for whichever combo
    in `bindings` (a list of (combo, on_trigger, enabled) triples) is
    pressed, swallowing the chord so the focused app never sees it. One
    listener - one low-level hook - serves every bound shortcut, instead
    of installing a separate hook per shortcut.

    Suppression is the whole point. Without it the shortcut would reach
    whatever has focus - press Ctrl+Alt+D in Word and you would get a
    lookup AND an inserted endnote. This mirrors make_listener() above,
    which already swallows the Forward button the same way.

    Raw Windows message constants (winuser.h):
      WM_KEYDOWN 0x0100, WM_KEYUP 0x0101
      WM_SYSKEYDOWN 0x0104, WM_SYSKEYUP 0x0105  - any chord holding Alt
      arrives as the SYS variants, so both pairs must be handled.
    """
    from pynput import keyboard

    WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
    WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0104, 0x0105
    VK_SHIFT, VK_CONTROL, VK_MENU = 0x10, 0x11, 0x12
    VK_LWIN, VK_RWIN = 0x5B, 0x5C

    listener = None  # bound below; filter only runs after start()
    # Whether we swallowed the key-down of the chord currently held, per
    # combo (keyed by id()). The matching key-up must be swallowed too: a
    # suppressed down followed by a delivered up leaves the app with a
    # dangling release, which some apps treat as a bare keypress.
    swallowed = {}

    def _down(vk):
        return win32api.GetAsyncKeyState(vk) < 0  # high bit = held now

    def _modifiers_match(combo):
        return (
            _down(VK_CONTROL) == combo.ctrl
            and _down(VK_MENU) == combo.alt
            and _down(VK_SHIFT) == combo.shift
            and (_down(VK_LWIN) or _down(VK_RWIN)) == combo.meta
        )

    def _filter(msg, data):
        for combo, on_trigger, enabled in bindings:
            if data.vkCode != combo.vk:
                continue  # different key entirely - not this binding

            if msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
                if not enabled.is_set() or not _modifiers_match(combo):
                    continue  # tool OFF, or wrong modifiers - not this one
                if not swallowed.get(id(combo)):
                    # Guard against key-repeat: holding the chord must not
                    # queue a lookup per repeat. Callback BEFORE
                    # suppress_event, which raises internally to abort the
                    # event, so nothing after it runs. Must be non-blocking.
                    swallowed[id(combo)] = True
                    on_trigger()
                listener.suppress_event()
                return True

            elif msg in (WM_KEYUP, WM_SYSKEYUP):
                # Match on our own bookkeeping, not on modifier state - by
                # the time the key comes up the user has often already let
                # go of Ctrl/Alt, so _modifiers_match() would be False here.
                if swallowed.get(id(combo)):
                    swallowed[id(combo)] = False
                    listener.suppress_event()
                    return True

        return True

    listener = keyboard.Listener(win32_event_filter=_filter)
    return listener
