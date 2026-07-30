"""Linux backend — EXPERIMENTAL, written to documented APIs, never run on
real hardware. Expect to debug before trusting.

Clipboard: xclip on X11, wl-paste/wl-copy on Wayland — whichever exists.
Install one:  sudo apt install xclip   (or wl-clipboard on Wayland).
Change detection is content-compare, same rationale as macOS.

Hook suppression: NOT POSSIBLE with pynput on X11 — the X11 backend can
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
    data = (text or "").encode("utf-8")
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
    # Keyboard-triggered lookups leave the chord's own keys held. Note the
    # vks here are Windows codes and X11 keysyms differ, so this is
    # best-effort — see win.send_copy for the reasoning.
    for vk in release_vks:
        try:
            _kbd.release(KeyCode.from_vk(vk))
        except Exception:
            pass
    _kbd.press(Key.ctrl)
    _kbd.press("c")
    _kbd.release("c")
    _kbd.release(Key.ctrl)


def make_listener(on_down, enabled):
    """Observe-only listener: X11 delivers button 9 (Forward) presses to us
    AND to the app under the cursor — no way to consume them with pynput.
    """
    from pynput import mouse

    def _on_click(x, y, button, pressed):
        # Button.button9 only exists on the X11 backend; compare by name so
        # this module stays importable everywhere.
        if pressed and getattr(button, "name", "") == "button9" and enabled.is_set():
            on_down()

    return mouse.Listener(on_click=_on_click)


def make_key_listener(combo, on_trigger, enabled):
    """Observe-only hotkey listener, for the same reason as make_listener:
    X11 delivers the chord to us AND to the focused app.

    GlobalHotKeys is the right tool here precisely because suppression is
    off the table anyway — on Windows and macOS we use a filtering hook
    instead. SUPPRESSES_HOTKEY is False so the UI can warn about this.
    """
    from pynput import keyboard

    def _fire():
        if enabled.is_set():
            on_trigger()

    return keyboard.GlobalHotKeys({combo.pynput_text(): _fire})
