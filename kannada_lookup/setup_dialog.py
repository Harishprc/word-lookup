"""One-time first-run setup, plus the shortcut recorder it shares.

Shown when data/settings.json doesn't exist (fresh clone, or first launch
after the multi-language update). The key field only appears when .env has
no GEMINI_API_KEY, so existing users just pick their language once.

The shortcut rows are also reachable later from the tray menu, because an
existing install never sees the first-run dialog again - see
ShortcutDialog at the bottom.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from . import config, hotkeys
from .languages import LANGUAGES
from .platforms import backend


class ShortcutRow:
    """A labelled QKeySequenceEdit plus Clear button and warning line.

    QKeySequenceEdit is Qt's own shortcut recorder - it captures the next
    chord the user presses and renders it properly. Hand-rolling key
    capture here would be strictly worse.
    """

    def __init__(self, layout, label: str, initial: str, hint: str = ""):
        layout.addWidget(QLabel(label))
        if hint:
            hint_label = QLabel(hint)
            hint_label.setWordWrap(True)
            hint_label.setStyleSheet("color: #666; font-size: 11px;")
            layout.addWidget(hint_label)

        row = QHBoxLayout()
        self.edit = QKeySequenceEdit()
        # One chord, not a Qt multi-key sequence: the OS hook can only
        # match a single combo.
        self.edit.setMaximumSequenceLength(1)
        if initial:
            self.edit.setKeySequence(QKeySequence(initial))
        row.addWidget(self.edit)

        clear = QPushButton("Clear")
        clear.setFixedWidth(60)
        clear.clicked.connect(self.edit.clear)
        row.addWidget(clear)
        layout.addLayout(row)

        self.warning = QLabel("")
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("color: #b3261e; font-size: 11px;")
        self.warning.hide()
        layout.addWidget(self.warning)

        self.edit.keySequenceChanged.connect(self._check)

    def _check(self):
        message = hotkeys.risk_warning(
            self.text(), getattr(backend, "SUPPRESSES_HOTKEY", True)
        )
        if message:
            self.warning.setText("⚠ " + message)
            self.warning.show()
        else:
            self.warning.hide()

    def text(self) -> str:
        """Canonical shortcut string, or "" when cleared/unusable."""
        return hotkeys.normalize(
            self.edit.keySequence().toString(QKeySequence.PortableText)
        )


def _suppression_note(layout):
    """On X11 the chord also reaches the focused app - say so up front
    rather than letting people discover it by breaking something."""
    if getattr(backend, "SUPPRESSES_HOTKEY", True):
        return
    note = QLabel(
        "Note: on Linux/X11 the shortcut cannot be intercepted, so the app "
        "you are using will also receive it. Pick a combination that does "
        "nothing there."
    )
    note.setWordWrap(True)
    note.setStyleSheet("color: #8a6d00; font-size: 11px;")
    layout.addWidget(note)


class SetupDialog(QDialog):
    def __init__(self):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        self.setWindowTitle("Word Lookup — one-time setup")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Translate English words into:"))
        self._combo = QComboBox()
        self._combo.addItems([entry["name"] for entry in LANGUAGES])
        self._combo.setCurrentText("Kannada")
        layout.addWidget(self._combo)

        self._key_edit = None
        if not config.GEMINI_API_KEY:
            key_label = QLabel(
                'Gemini API key — free, no card: <a href="https://aistudio.google.com">'
                "aistudio.google.com</a> → Get API key"
            )
            key_label.setOpenExternalLinks(True)
            layout.addWidget(key_label)
            self._key_edit = QLineEdit()
            self._key_edit.setPlaceholderText("Paste your API key here")
            layout.addWidget(self._key_edit)

        self._lookup_row = ShortcutRow(
            layout,
            "Lookup shortcut (optional):",
            config.LOOKUP_HOTKEY,
            "For laptops with no Forward button. Click the box and press "
            "the keys you want. Leave empty to use the mouse only.",
        )
        _suppression_note(layout)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save_and_accept(self):
        if self._key_edit is not None:
            key = self._key_edit.text().strip()
            if not key:
                self._key_edit.setPlaceholderText("Key required — paste it here")
                return
            config.save_api_key(key)
        config.update_settings(
            target_language=self._combo.currentText(),
            lookup_hotkey=self._lookup_row.text(),
        )
        self.accept()


class ShortcutDialog(QDialog):
    """Just the shortcut rows, opened from the tray menu.

    Exists because SetupDialog only ever appears once. Without this an
    existing install - anyone who upgraded from v0.1.0 - would have no way
    to set a keyboard shortcut at all.
    """

    def __init__(self):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        self.setWindowTitle("Word Lookup — shortcuts")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self._lookup_row = ShortcutRow(
            layout,
            "Lookup shortcut:",
            config.LOOKUP_HOTKEY,
            "Alternative to the mouse Forward button, for laptops. "
            "Leave empty to use the mouse only.",
        )
        self._toggle_row = ShortcutRow(
            layout,
            "Toggle ON/OFF shortcut:",
            config.TOGGLE_HOTKEY,
            "Switches Word Lookup on and off. Works even while it is off.",
        )
        _suppression_note(layout)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save_and_accept(self):
        config.update_settings(
            lookup_hotkey=self._lookup_row.text(),
            toggle_hotkey=self._toggle_row.text(),
        )
        self.accept()


def run_setup_if_needed() -> bool:
    """True = ready to run (setup done or already configured);
    False = user cancelled setup, caller should exit."""
    if config.load_settings() is not None:
        return True
    dialog = SetupDialog()
    return dialog.exec() == QDialog.Accepted
