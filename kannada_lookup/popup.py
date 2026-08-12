"""Frameless floating dictionary card shown near the mouse cursor.

PySide6 (Qt) chosen over Tkinter deliberately: Qt shapes complex scripts
through HarfBuzz, so Indic conjuncts (ಕ್ಕ, क्ष…) render correctly.
Windows Tk often breaks these.

Card layout (rows collapse when their field is empty):
    word (bold) · part of speech
    meaning                 — plain-English meaning
    synonyms                — 2-3 conversational synonyms, italic
    ── divider ──
    translation             — target-language translation
    synonyms (native)       — 2-3 synonyms of the translation, italic
    example                 — one native example sentence, italic

WA_ShowWithoutActivating + Tool window flags mean the popup NEVER steals
focus. WA_TranslucentBackground is required for real rounded corners: the
top-level window paints nothing, the inner #card frame carries the radius —
otherwise the corner pixels would show as opaque squares over the app below.
"""

from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QColor, QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from . import config
from .translator import LookupResult

# "Nirmala UI" covers every Indic script on Windows; "Noto Sans Kannada"
# preferred where installed; anything else (CJK, Arabic, Cyrillic…) falls
# through to Qt's automatic font fallback.
_NATIVE_FONTS = '"Noto Sans Kannada", "Nirmala UI", "Segoe UI"'

_STYLE = f"""
QFrame#card {{
    /* off-white -> faint blue, top to bottom; borderless by request */
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #fdfdfe, stop:1 #edf2fb);
    border: none;
    border-radius: 12px;
}}
QLabel#word {{
    color: #1a1a1a;
    font-size: 14pt;
    font-weight: bold;
}}
QLabel#pos {{
    color: #8a8f9c;
    font-size: 10.5pt;
    font-style: italic;
}}
QLabel#meaning {{
    color: #333333;
    font-size: 11pt;
}}
QLabel#synonyms {{
    color: #6a6a6a;
    font-size: 10.5pt;
    font-style: italic;
}}
QFrame#divider {{
    background-color: #e2e7f0;
    border: none;
}}
QLabel#translation {{
    color: #111111;
    font-family: {_NATIVE_FONTS};
    font-size: 16pt;
}}
/* Synonyms of the translation. Same muted italic treatment as the English
   synonyms row so the two halves of the card read symmetrically, but in
   the native font — Segoe UI has no Indic glyphs. */
QLabel#synonymsNative {{
    color: #6a6a6a;
    font-family: {_NATIVE_FONTS};
    font-size: 11pt;
    font-style: italic;
}}
QLabel#example {{
    color: #555555;
    font-family: {_NATIVE_FONTS};
    font-size: 12pt;
    font-style: italic;
}}
"""

# Window margin around the card — room for the drop shadow to render.
_SHADOW_MARGIN = 16


class LookupPopup(QWidget):
    """Singleton-style popup: each show_* call replaces current contents."""

    def __init__(self):
        super().__init__(
            None,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool,
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(_STYLE)

        self._card = QFrame(objectName="card")

        shadow = QGraphicsDropShadowEffect(self._card)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 60))
        self._card.setGraphicsEffect(shadow)

        self._word = QLabel(objectName="word")
        self._pos = QLabel(objectName="pos")  # part of speech, beside word
        self._meaning = QLabel(objectName="meaning")
        self._synonyms = QLabel(objectName="synonyms")
        self._translation = QLabel(objectName="translation")
        self._synonyms_native = QLabel(objectName="synonymsNative")
        self._example = QLabel(objectName="example")
        self._labels = (
            self._word,
            self._pos,
            self._meaning,
            self._synonyms,
            self._translation,
            self._synonyms_native,
            self._example,
        )
        for lbl in self._labels:
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.NoTextInteraction)
        self._pos.setWordWrap(False)  # short tag; wrapping looks broken

        self._divider = QFrame(objectName="divider")
        self._divider.setFixedHeight(1)

        # word + part-of-speech share one row, baseline-ish aligned.
        word_row = QHBoxLayout()
        word_row.setSpacing(8)
        word_row.addWidget(self._word)
        word_row.addWidget(self._pos, alignment=Qt.AlignBottom)
        word_row.addStretch(1)

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(4)
        card_layout.addLayout(word_row)
        card_layout.addWidget(self._meaning)
        card_layout.addWidget(self._synonyms)
        card_layout.addWidget(self._divider)
        card_layout.addWidget(self._translation)
        card_layout.addWidget(self._synonyms_native)
        card_layout.addWidget(self._example)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(*([_SHADOW_MARGIN] * 4))
        outer.addWidget(self._card)

        self.setMaximumWidth(460)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    # --- public API (call on GUI thread only) --------------------------

    def show_loading(self, original_hint=""):
        """Instant feedback at the cursor while capture+API run."""
        self._anchor = QCursor.pos()
        self._set_texts(word=original_hint, translation="…")
        self._present(timeout_ms=0)  # no auto-dismiss while loading

    def show_result(self, result: LookupResult):
        self._set_texts(
            word=result.original,
            pos=f"· {result.part_of_speech}" if result.part_of_speech else "",
            meaning=result.meaning,
            synonyms=result.synonyms,
            translation=result.translation,
            synonyms_native=result.synonyms_native,
            example=result.example_native,
        )
        self._present(timeout_ms=config.POPUP_TIMEOUT_MS)

    def show_message(self, message, timeout_ms=2500):
        """Short status: 'no selection', errors, ON/OFF confirmation."""
        self._anchor = QCursor.pos()
        self._set_texts(translation=message)
        self._present(timeout_ms=timeout_ms)

    # --- internals ------------------------------------------------------

    def _set_texts(self, word="", pos="", meaning="", synonyms="",
                   translation="", example="", synonyms_native=""):
        """Fill rows; empty ones collapse. Divider only separates the two
        halves — hidden when the English half has nothing to separate."""
        self._word.setText(word)
        self._pos.setText(pos)
        self._meaning.setText(meaning)
        self._synonyms.setText(synonyms)
        self._translation.setText(translation)
        self._synonyms_native.setText(synonyms_native)
        self._example.setText(example)
        for lbl in self._labels:
            lbl.setVisible(bool(lbl.text()))
        english_half = bool(meaning or synonyms)
        native_half = bool(translation or example)
        self._divider.setVisible(english_half and native_half)

    def _present(self, timeout_ms):
        self._timer.stop()
        self.adjustSize()
        self.move(self._clamped(getattr(self, "_anchor", QCursor.pos())))
        self.show()
        if timeout_ms:
            self._timer.start(timeout_ms)

    def _clamped(self, anchor: QPoint) -> QPoint:
        """Offset from cursor, kept fully on the cursor's screen. The
        shadow margin is transparent window space — subtract it so the
        visible card (not the invisible margin) sits 12/18px from cursor."""
        pos = anchor + QPoint(12 - _SHADOW_MARGIN, 18 - _SHADOW_MARGIN)
        screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = min(max(pos.x(), geo.left()), geo.right() - self.width())
        y = min(max(pos.y(), geo.top()), geo.bottom() - self.height())
        return QPoint(x, y)

    def mousePressEvent(self, event):  # click popup to dismiss
        self.hide()
        event.accept()
