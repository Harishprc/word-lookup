"""Global mouse hook: fire a callback on the Forward side button.

All OS-specific mechanics (raw message filtering, event suppression,
button numbering) live in kannada_lookup/platforms/ — this module only
adds the shared debounce and lifecycle.

Per-OS behavior (see each platforms/ module for detail):
  Windows  — SetWindowsHookEx WH_MOUSE_LL via pynput; XButton2 swallowed
             so the app underneath never sees "Forward". No admin needed
             (but a user-session hook can't observe elevated windows).
  macOS    — Quartz event tap; swallows the click; needs Accessibility +
             Input Monitoring permissions. EXPERIMENTAL.
  Linux    — X11 observe-only; the app also receives the click (X11 can't
             consume events via pynput). EXPERIMENTAL.
"""

import threading
import time

from . import config
from .platforms import backend


class XButtonHook:
    """Listens system-wide for the Forward button; calls `on_trigger` on
    press, debounced so button-mashing can't queue lookups.

    `enabled` is a threading.Event shared with the tray icon / hotkey:
    set = active, cleared = dormant (button passes through where the OS
    allows suppression at all). Toggling never reinstalls the hook.
    """

    def __init__(self, on_trigger, enabled: threading.Event):
        self._on_trigger = on_trigger
        self._last_fire = 0.0
        self._listener = backend.make_listener(self._debounced, enabled)

    def _debounced(self):
        now = time.monotonic()
        if now - self._last_fire >= config.DEBOUNCE_S:
            self._last_fire = now
            self._on_trigger()  # must be non-blocking (emits a Qt signal)

    def start(self):
        self._listener.start()

    def stop(self):
        self._listener.stop()
