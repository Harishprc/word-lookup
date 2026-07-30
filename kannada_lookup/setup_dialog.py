"""One-time first-run setup: pick a target language, paste the API key.

Shown when data/settings.json doesn't exist (fresh clone, or first launch
after the multi-language update). The key field only appears when .env has
no GEMINI_API_KEY, so existing users just pick their language once.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from . import config
from .languages import LANGUAGES


class SetupDialog(QDialog):
    def __init__(self):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        self.setWindowTitle("Word Lookup — one-time setup")
        self.setMinimumWidth(380)

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
        config.save_settings(self._combo.currentText())
        self.accept()


def run_setup_if_needed() -> bool:
    """True = ready to run (setup done or already configured);
    False = user cancelled setup, caller should exit."""
    if config.load_settings() is not None:
        return True
    dialog = SetupDialog()
    return dialog.exec() == QDialog.Accepted
