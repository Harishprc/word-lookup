"""Wires everything together: hook → capture → translate → popup.

Threading model (the part that usually bites):
  - Qt MUST own the main thread → QApplication + popup + tray live there.
  - pynput's mouse hook and the global-hotkey listener each run their own
    thread. They never touch Qt directly - they emit Qt signals, which Qt
    delivers to the GUI thread via queued connections (thread-safe).
  - Each lookup (Ctrl+C round-trip + HTTP call, both blocking) runs in a
    short-lived worker thread so the popup and hook stay responsive.
"""

import threading
from pathlib import Path
from tempfile import gettempdir

from PySide6.QtCore import QLockFile, QObject, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QIcon,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import capture, config, hotkeys, languages
from .hook import KeyComboHook, XButtonHook
from .popup import LookupPopup
from .translator import LookupFailed, make_provider


class Bridge(QObject):
    """Signals crossing from listener/worker threads into the GUI thread."""

    # Payload is the tuple of virtual-key codes the user is still holding
    # (empty for the mouse button, the shortcut's key for the hotkey).
    triggered = Signal(object)           # lookup requested (hook thread)
    toggle_requested = Signal()          # toggle shortcut (hook thread)
    lookup_done = Signal(object)         # LookupResult (worker thread)
    lookup_failed = Signal(str)          # message (worker thread)


def _tray_icon(active: bool) -> QIcon:
    """Tiny generated icon: a native glyph of the target language in a
    circle (ಕ for Kannada, अ for Hindi…). Gray when disabled."""
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#7c5cff") if active else QColor("#6b6f7a"))
    p.setPen(Qt.NoPen)
    p.drawEllipse(2, 2, 60, 60)
    p.setPen(QColor("white"))
    font = p.font()
    font.setPixelSize(36)
    font.setFamilies(["Noto Sans Kannada", "Nirmala UI", "Segoe UI"])
    p.setFont(font)
    p.drawText(pm.rect(), Qt.AlignCenter, config.LANGUAGE_GLYPH)
    p.end()
    return QIcon(pm)


class App:
    def __init__(self, qapp: QApplication):
        self.qapp = qapp  # created in main() so the lock check runs first

        self.popup = LookupPopup()
        self.bridge = Bridge()
        self.enabled = threading.Event()
        self.enabled.set()  # starts ON each launch; state is session-only
        self._busy = False

        # Provider is created lazily on first lookup so a missing API key
        # shows as a popup message instead of killing the app at startup.
        self._provider = None

        self.bridge.triggered.connect(self._on_trigger)
        self.bridge.toggle_requested.connect(self._toggle)
        self.bridge.lookup_done.connect(self._on_done)
        self.bridge.lookup_failed.connect(self._on_failed)

        self._build_tray()

        self.hook = XButtonHook(
            lambda: self.bridge.triggered.emit(()), self.enabled
        )
        self.hook.start()

        # Keyboard shortcuts go through the same suppressing hook as the
        # mouse button, so the chord never reaches the focused app. Both
        # are optional and rebuilt in place when the user changes them.
        self.key_hook = None
        self._install_shortcuts()

        # Startup sync. No-ops instantly if GITHUB_PAT isn't set.
        self._run_sync()

    # --- keyboard shortcuts ----------------------------------------------

    def _install_shortcuts(self):
        """(Re)bind the lookup and toggle shortcuts from current config.

        Both share a single OS-level hook (KeyComboHook) instead of one
        installation each. Called at startup and again after the recorder
        saves, so changing a shortcut takes effect without restarting.
        """
        if self.key_hook is not None:
            try:
                self.key_hook.stop()
            except Exception:
                pass  # a listener that never started can't be stopped
            self.key_hook = None

        bindings = []

        lookup = hotkeys.parse(config.LOOKUP_HOTKEY)
        if lookup is not None:
            bindings.append((
                lookup,
                # The shortcut's own key is still held when this fires;
                # pass it along so the copy chord isn't polluted.
                lambda vk=lookup.vk: self.bridge.triggered.emit((vk,)),
                self.enabled,
                False,
            ))

        toggle = hotkeys.parse(config.TOGGLE_HOTKEY)
        if toggle is not None:
            bindings.append((
                toggle,
                self.bridge.toggle_requested.emit,
                self.enabled,
                True,  # always_on - must work while the tool is OFF
            ))

        if bindings:
            self.key_hook = KeyComboHook(bindings)
            self.key_hook.start()

    # --- tray -----------------------------------------------------------

    def _build_tray(self):
        self.tray = QSystemTrayIcon(_tray_icon(True))
        menu = QMenu()

        self.enabled_action = QAction("Enabled", menu, checkable=True, checked=True)
        self.enabled_action.triggered.connect(self._toggle)
        menu.addAction(self.enabled_action)

        self.hotkey_hint = QAction("", menu)
        self.hotkey_hint.setEnabled(False)
        menu.addAction(self.hotkey_hint)
        self._sync_hotkey_hint()

        shortcuts_action = QAction("Change shortcuts…", menu)
        shortcuts_action.triggered.connect(self._change_shortcuts)
        menu.addAction(shortcuts_action)

        self._build_language_menu(menu)

        register_action = QAction("Open word register", menu)
        register_action.triggered.connect(self._open_register)
        menu.addAction(register_action)

        menu.addSeparator()
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self._menu = menu  # keep a reference; tray does not own it
        self._sync_tray()
        self.tray.show()

    def _build_language_menu(self, menu):
        """Submenu to switch target language without deleting settings.json
        and restarting, which was the only way before."""
        lang_menu = menu.addMenu("Translation language")
        self._lang_group = QActionGroup(menu)
        self._lang_group.setExclusive(True)

        for entry in languages.LANGUAGES:
            action = QAction(
                f"{entry['glyph']}   {entry['name']}", menu, checkable=True
            )
            action.setChecked(entry["name"] == config.TARGET_LANGUAGE)
            # name= binds per-iteration; a bare closure would capture the
            # loop variable and every item would pick the last language.
            action.triggered.connect(
                lambda _checked=False, name=entry["name"]: self._change_language(name)
            )
            self._lang_group.addAction(action)
            lang_menu.addAction(action)

    def _change_language(self, name: str):
        if name == config.TARGET_LANGUAGE:
            return
        config.save_settings(name)  # persists, then refreshes config globals

        # The provider is cached and takes the language at construction
        # (make_provider reads config.TARGET_LANGUAGE), so without dropping
        # it here every later lookup would keep translating into the old
        # language while the tray icon claimed otherwise. The cache itself
        # is keyed per-language, so nothing already stored is lost.
        self._provider = None

        self._sync_tray()  # repaints the glyph and updates the tooltip
        self.popup.show_message(f"Language: {name}")

    def _sync_tray(self):
        on = self.enabled.is_set()
        self.tray.setIcon(_tray_icon(on))
        self.tray.setToolTip(
            f"{config.TARGET_LANGUAGE} Lookup — {'ON' if on else 'OFF'}"
        )
        self.enabled_action.setChecked(on)

    def _sync_hotkey_hint(self):
        """Tray line showing the current bindings. The lookup shortcut is
        optional, so say so rather than showing a blank."""
        lookup = config.LOOKUP_HOTKEY or "not set (mouse Forward button)"
        self.hotkey_hint.setText(
            f"Lookup: {lookup}   •   Toggle: {config.TOGGLE_HOTKEY}"
        )

    def _change_shortcuts(self):
        """Open the recorder so shortcuts can be changed after first run -
        without this, an existing install could never reach the dialog,
        since it only appears when settings.json is missing."""
        from .setup_dialog import ShortcutDialog

        if ShortcutDialog().exec():
            self._install_shortcuts()
            self._sync_hotkey_hint()
            self.popup.show_message("Shortcuts updated")

    def _open_register(self):
        """Regenerate the HTML word register and open it in the browser.
        See register.generate_and_open for why this opens a raw path and
        never a file:// URI."""
        from . import register

        register.generate_and_open()

    # --- sync -------------------------------------------------------------

    def _run_sync(self):
        """Runs sync.sync_now() on a worker thread - it's a network call,
        must never block the GUI thread.

        Fires once at startup and reports nothing: sync is opt-in (it
        no-ops entirely without GITHUB_PAT) and a popup on every launch
        would be noise. Failures are swallowed for the same reason they
        always were - sync must never take a lookup down with it."""
        def worker():
            try:
                from . import sync

                sync.sync_now()
            except Exception:  # sync must never crash the app
                pass

        threading.Thread(target=worker, daemon=True).start()

    # --- toggle ----------------------------------------------------------

    def _toggle(self):
        if self.enabled.is_set():
            self.enabled.clear()
        else:
            self.enabled.set()
        self._sync_tray()
        self.popup.show_message(
            f"Word Lookup {'ON' if self.enabled.is_set() else 'OFF'}"
        )

    # --- lookup flow ------------------------------------------------------

    def _on_trigger(self, release_vks=()):
        if self._busy:
            return  # one lookup at a time
        self._busy = True
        self.popup.show_loading()
        threading.Thread(
            target=self._worker, args=(release_vks,), daemon=True
        ).start()

    def _worker(self, release_vks=()):
        """Blocking part: clipboard round-trip + API call. Worker thread."""
        try:
            text = capture.grab_selection(release_vks)
            if not text:
                self.bridge.lookup_failed.emit("No text selected")
                return
            if self._provider is None:
                self._provider = make_provider()
            result = self._provider.lookup(text)
            self.bridge.lookup_done.emit(result)
        except LookupFailed as e:
            self.bridge.lookup_failed.emit(str(e))
        except Exception as e:  # never let a lookup crash the app
            self.bridge.lookup_failed.emit(f"Unexpected error: {e}")

    def _on_done(self, result):
        self._busy = False
        self.popup.show_result(result)

    def _on_failed(self, message):
        self._busy = False
        self.popup.show_message(message, is_error=True)

    # --- lifecycle ---------------------------------------------------------

    def _quit(self):
        self.hook.stop()
        if self.key_hook is not None:
            self.key_hook.stop()
        self.tray.hide()
        self.qapp.quit()

    def run(self):
        return self.qapp.exec()


def main():
    # Single-instance guard: with both an autostart shortcut and a desktop
    # shortcut, double-launching is easy - two instances would mean two
    # hooks and doubled popups. QLockFile auto-detects stale locks from
    # crashed processes, so a crash never bricks future launches.
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)

    lock = QLockFile(str(Path(gettempdir()) / "kannada_lookup.lock"))
    lock.setStaleLockTime(0)  # rely on PID liveness check, not a timer
    if not lock.tryLock(100):
        from .popup import LookupPopup

        popup = LookupPopup()
        popup.show_message("Word Lookup is already running (check tray)")
        QTimer.singleShot(2600, app.quit)
        app.exec()
        raise SystemExit(0)

    # One-time setup (target language + key) before anything else starts.
    from .setup_dialog import run_setup_if_needed

    if not run_setup_if_needed():
        lock.unlock()
        raise SystemExit(0)  # user cancelled setup

    instance = App(app)
    try:
        raise SystemExit(instance.run())
    finally:
        lock.unlock()


if __name__ == "__main__":
    main()
