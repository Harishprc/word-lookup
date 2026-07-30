"""OS-detection layer: everything platform-specific lives behind here.

Two things differ per OS and nothing else does:
  1. Clipboard access (snapshot / read / write / detect-change)
  2. How the global mouse hook suppresses the XButton2 click

Each backend module exposes the same surface:
  read_text() -> str|None
  write_text(text) -> None
  change_token() -> object      # value that changes when clipboard changes
  send_copy() -> None           # synthetic Ctrl+C (Cmd+C on macOS)
  make_listener(on_down, enabled) -> pynput.mouse.Listener
  SUPPRESSES_CLICK: bool        # False where the OS can't swallow events

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
