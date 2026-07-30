"""OS-detection layer: everything platform-specific lives behind here.

Three things differ per OS and nothing else does:
  1. Clipboard access (snapshot / read / write / detect-change)
  2. How the global mouse hook suppresses the XButton2 click
  3. How the global key hook suppresses the lookup shortcut

Each backend module exposes the same surface:
  read_text() -> str|None
  write_text(text) -> None
  change_token() -> object      # value that changes when clipboard changes
  send_copy(release_vks=()) -> None
                                # synthetic Ctrl+C (Cmd+C on macOS);
                                # release_vks are keys the user is still
                                # holding from a keyboard trigger
  make_listener(on_down, enabled) -> pynput.mouse.Listener
  make_key_listener(combo, on_trigger, enabled) -> listener
                                # combo is a hotkeys.Combo
  SUPPRESSES_CLICK: bool        # False where the OS can't swallow events
  SUPPRESSES_HOTKEY: bool       # ditto for the keyboard shortcut

Suppression matters more than it looks: an unsuppressed shortcut reaches
the focused app as well, so Ctrl+Alt+D in Word would insert an endnote
alongside the lookup. Windows and macOS can swallow it; X11 cannot.

Windows is the only backend tested on real hardware. macOS and Linux are
best-effort implementations of the documented pynput/clipboard APIs —
EXPERIMENTAL, see README before relying on them.
"""

import sys

if sys.platform == "win32":
    from . import win as backend
elif sys.platform == "darwin":
    from . import mac as backend
else:
    from . import linux as backend

__all__ = ["backend"]
