"""Wires everything together: hook → capture → translate → popup.

Threading model (the part that usually bites):
  - Qt MUST own the main thread → QApplication + popup + tray live there.
  - pynput's mouse hook and the global-hotkey listener each run their own
    thread. They never touch Qt directly — they emit Qt signals, which Qt
    delivers to the GUI thread via queued connections (thread-safe).
  - Each lookup (Ctrl+C round-trip + HTTP call, both blocking) runs in a
    short-lived worker thread so the popup and hook stay responsive.
"""

import threading
from pathlib import Path
from tempfile import gettempdir

from pynput import keyboard
from PySide6.QtCore import QLockFile, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import capture, config
from .hook import XButtonHook
from .popup import LookupPopup
from .translator import LookupFailed, make_provider


class Bridge(QObject):
    """Signals crossing from listener/worker threads into the GUI thread."""

    triggered = Signal()                 # XButton2 pressed (hook thread)
    toggle_requested = Signal()          # hotkey pressed (hotkey thread)
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

        self.hook = XButtonHook(self.bridge.triggered.emit, self.enabled)
        self.hook.start()

        # Global toggle hotkey — works even when the tray is out of reach.
        self.hotkeys = keyboard.GlobalHotKeys(
            {config.TOGGLE_HOTKEY: self.bridge.toggle_requested.emit}
        )
        self.hotkeys.start()

    # --- tray -----------------------------------------------------------

    def _build_tray(self):
        self.tray = QSystemTrayIcon(_tray_icon(True))
        menu = QMenu()

        self.enabled_action = QAction("Enabled", menu, checkable=True, checked=True)
        self.enabled_action.triggered.connect(self._toggle)
        menu.addAction(self.enabled_action)

        hotkey_hint = QAction(
            f"Toggle hotkey: {config.TOGGLE_HOTKEY.replace('<', '').replace('>', '')}",
            menu,
        )
        hotkey_hint.setEnabled(False)
        menu.addAction(hotkey_hint)

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

    def _sync_tray(self):
        on = self.enabled.is_set()
        self.tray.setIcon(_tray_icon(on))
        self.tray.setToolTip(
            f"{config.TARGET_LANGUAGE} Lookup — {'ON' if on else 'OFF'}"
        )
        self.enabled_action.setChecked(on)

    def _open_register(self):
        """Regenerate the HTML word register and open it in the browser."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from . import register

        path = register.generate()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

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

    def _on_trigger(self):
        if self._busy:
            return  # one lookup at a time
        self._busy = True
        self.popup.show_loading()
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        """Blocking part: clipboard round-trip + API call. Worker thread."""
        try:
            text = capture.grab_selection()
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
        self.popup.show_message(message)

    # --- lifecycle ---------------------------------------------------------

    def _quit(self):
        self.hook.stop()
        self.hotkeys.stop()
        self.tray.hide()
        self.qapp.quit()

    def run(self):
        return self.qapp.exec()


def main():
    # Single-instance guard: with both an autostart shortcut and a desktop
    # shortcut, double-launching is easy — two instances would mean two
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
