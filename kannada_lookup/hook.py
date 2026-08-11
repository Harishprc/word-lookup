"""Global input hooks: fire a callback on the Forward side button, or on
a user-chosen keyboard shortcut.

The shortcut exists for laptops, which have no side buttons at all. Both
hooks share one debounce and one enabled-flag contract.

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


# A permanently-set Event, so the toggle shortcut is never gated by the
# very flag it exists to flip.
_ALWAYS_SET = threading.Event()
_ALWAYS_SET.set()


class _DebouncedHook:
    """Shared lifecycle + debounce. Subclasses only pick the listener.

    `enabled` is a threading.Event shared with the tray icon: set =
    active, cleared = dormant (the trigger passes through where the OS
    allows suppression at all). Toggling never reinstalls the hook.
    """

    def __init__(self, on_trigger):
        self._on_trigger = on_trigger
        self._last_fire = 0.0
        self._listener = None  # subclass sets this before start()

    def _debounced(self):
        now = time.monotonic()
        if now - self._last_fire >= config.DEBOUNCE_S:
            self._last_fire = now
            self._on_trigger()  # must be non-blocking (emits a Qt signal)

    def start(self):
        self._listener.start()

    def stop(self):
        self._listener.stop()


class XButtonHook(_DebouncedHook):
    """Listens system-wide for the Forward button; calls `on_trigger` on
    press, debounced so button-mashing can't queue lookups."""

    def __init__(self, on_trigger, enabled: threading.Event):
        super().__init__(on_trigger)
        self._listener = backend.make_listener(self._debounced, enabled)


class KeyComboHook:
    """One shared OS-level keyboard hook serving every bound shortcut —
    the lookup shortcut (laptop alternative to the Forward button) and the
    ON/OFF toggle both go through this, instead of one hook installation
    each. Every keystroke on the system only has to pass through a single
    filter no matter how many shortcuts are configured.

    On Windows and macOS the backend swallows the chord so the focused app
    never sees it; on X11 it cannot (backend.SUPPRESSES_HOTKEY says which).

    `bindings` is a list of (combo, on_trigger, enabled, always_on)
    tuples. `always_on` is for the toggle: the toggle shortcut has to keep
    working while the tool is OFF, otherwise there would be no way to
    switch it back on from the keyboard. Each binding gets its own
    debounce timer so one shortcut firing rapidly can't suppress another.
    """

    def __init__(self, bindings):
        self._listener = backend.make_key_listener([
            (combo, self._debounced(on_trigger),
             _ALWAYS_SET if always_on else enabled)
            for combo, on_trigger, enabled, always_on in bindings
        ])

    @staticmethod
    def _debounced(on_trigger):
        last_fire = [0.0]

        def _fire():
            now = time.monotonic()
            if now - last_fire[0] >= config.DEBOUNCE_S:
                last_fire[0] = now
                on_trigger()  # must be non-blocking (emits a Qt signal)

        return _fire

    def start(self):
        self._listener.start()

    def stop(self):
        self._listener.stop()
