"""Linux backend - EXPERIMENTAL, written to documented APIs, never run on
real hardware. Expect to debug before trusting.

Clipboard: xclip on X11, wl-paste/wl-copy on Wayland - whichever exists.
Install one:  sudo apt install xclip   (or wl-clipboard on Wayland).
Change detection is content-compare, same rationale as macOS.

Hook suppression: NOT POSSIBLE with pynput on X11 - the X11 backend can
observe events but cannot consume them, so the Forward click ALSO reaches
the app under the cursor (browser may navigate forward on lookup). This
is a documented platform limitation, not a bug here. SUPPRESSES_CLICK is
False so hook.py knows not to try.
"""

import shutil
import subprocess

from pynput.keyboard import Controller, Key, KeyCode

SUPPRESSES_CLICK = False
# Same X11 limitation applies to the keyboard: GlobalHotKeys observes but
# cannot consume, so the shortcut ALSO reaches the focused app. The
# recorder warns the user about this when the flag is False.
SUPPRESSES_HOTKEY = False
# change_token() is a content compare here, so capture.py can't tell "the
# selection copied but happened to match what was already on the
# clipboard" apart from "nothing was selected". See capture.grab_selection.
TOKEN_IS_CONTENT = True

_kbd = Controller()

_HAS_XCLIP = shutil.which("xclip") is not None
_HAS_WL = shutil.which("wl-paste") is not None


def read_text():
    try:
        if _HAS_XCLIP:
            out = subprocess.run(
                ["xclip", "-selection", "clipboard", "-o"],
                capture_output=True, timeout=2,
            )
        elif _HAS_WL:
            out = subprocess.run(["wl-paste", "--no-newline"],
                                 capture_output=True, timeout=2)
        else:
            return None
        return out.stdout.decode("utf-8", errors="replace") or None
    except Exception:
        return None


def write_text(text):
    # None means the original clipboard content couldn't be read - leave
    # the clipboard alone rather than overwriting it with an empty string.
    if text is None:
        return
    data = text.encode("utf-8")
    try:
        if _HAS_XCLIP:
            subprocess.run(["xclip", "-selection", "clipboard"],
                           input=data, timeout=2)
        elif _HAS_WL:
            subprocess.run(["wl-copy"], input=data, timeout=2)
    except Exception:
        pass


def change_token():
    return read_text()


def send_copy(release_vks=()):
    for mod in (Key.shift, Key.shift_r, Key.alt):
        _kbd.release(mod)
    # Keyboard-triggered lookups leave the chord's own keys held. `vk` is a
    # Windows virtual-key code (hotkeys.Combo.vk) and X11 keysyms differ, so
    # KeyCode.from_vk(vk) targets the wrong key in general. For letters/
    # digits the Windows VK happens to equal the ASCII code, so
    # KeyCode.from_char() releases the right key regardless of platform
    # (pynput resolves the native keysym itself). Anything else (named/
    # punctuation keys) has no reliable translation available -
    # best-effort fall back to from_vk, same as before.
    for vk in release_vks:
        try:
            if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:  # '0'-'9', 'A'-'Z'
                _kbd.release(KeyCode.from_char(chr(vk).lower()))
            else:
                _kbd.release(KeyCode.from_vk(vk))
        except Exception:
            pass
    _kbd.press(Key.ctrl)
    _kbd.press("c")
    _kbd.release("c")
    _kbd.release(Key.ctrl)


def make_listener(on_down, enabled):
    """Observe-only listener: X11 delivers button 9 (Forward) presses to us
    AND to the app under the cursor - no way to consume them with pynput.
    """
    from pynput import mouse

    def _on_click(x, y, button, pressed):
        # Button.button9 only exists on the X11 backend; compare by name so
        # this module stays importable everywhere.
        if pressed and getattr(button, "name", "") == "button9" and enabled.is_set():
            on_down()

    return mouse.Listener(on_click=_on_click)


def make_key_listener(bindings):
    """Observe-only hotkey listener, for the same reason as make_listener:
    X11 delivers the chord to us AND to the focused app. `bindings` is a
    list of (combo, on_trigger, enabled) triples - GlobalHotKeys already
    accepts a dict of chords, so every bound shortcut shares one listener.

    GlobalHotKeys is the right tool here precisely because suppression is
    off the table anyway - on Windows and macOS we use a filtering hook
    instead. SUPPRESSES_HOTKEY is False so the UI can warn about this.
    """
    from pynput import keyboard

    def _make_fire(on_trigger, enabled):
        def _fire():
            if enabled.is_set():
                on_trigger()

        return _fire

    chords = {
        combo.pynput_text(): _make_fire(on_trigger, enabled)
        for combo, on_trigger, enabled in bindings
    }
    return keyboard.GlobalHotKeys(chords)
