"""Frameless floating dictionary card shown near the mouse cursor.

PySide6 (Qt) chosen over Tkinter deliberately: Qt shapes complex scripts
through HarfBuzz, so Indic conjuncts (ಕ್ಕ, क्ष…) render correctly.
Windows Tk often breaks these.

Card layout (rows collapse when their field is empty):
    word (bold) · part of speech
    meaning                          - plain-English meaning
    synonyms                         - 2-3 conversational synonyms, italic
    example (English)                - one example sentence, italic
    ── divider ──
    translation (bold) · synonyms (native, in parens) - same row
    example (native)                 - one example sentence, italic

A small dot at the card's top-right corner shows outcome at a glance:
green for a successful lookup, red for an error. Hidden while loading or
for a plain status toast (language switched, shortcuts updated, …) -
those aren't a lookup result, so neither color would be honest.

WA_ShowWithoutActivating + Tool window flags mean the popup NEVER steals
focus. WA_TranslucentBackground is required for real rounded corners: the
top-level window paints nothing, the inner #card frame carries the radius -
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
/* #6a6a6a, not the #8a8f9c this used to be: at 10.5pt that measured
   2.88:1 against the card, below the 4.5:1 WCAG AA needs for text this
   size. #6a6a6a reaches 4.82:1 and is a grey already used elsewhere on
   the card, so the palette gets shorter as well as legible. */
QLabel#pos {{
    color: #6a6a6a;
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
QLabel#exampleEn {{
    color: #555555;
    font-size: 11pt;
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
    font-weight: bold;
}}
/* Synonyms of the translation, beside it on the same row (see
   translation_row in __init__) rather than its own line — reads as
   "word (synonym, synonym)" instead of a separate labelled row, matching
   how a paper dictionary sets a headword's synonyms. Same muted-italic
   treatment as the English synonyms row, native font since Segoe UI has
   no Indic glyphs. */
QLabel#synonymsNative {{
    color: #6a6a6a;
    font-family: {_NATIVE_FONTS};
    font-size: 11pt;
    font-style: italic;
}}
QLabel#example {{
    color: #555555;
    font-family: {_NATIVE_FONTS};
    font-size: 13pt;
    font-style: italic;
}}
"""

# Window margin around the card - room for the drop shadow to render.
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
        self._example_en = QLabel(objectName="exampleEn")
        self._translation = QLabel(objectName="translation")
        self._synonyms_native = QLabel(objectName="synonymsNative")
        self._example = QLabel(objectName="example")
        self._labels = (
            self._word,
            self._pos,
            self._meaning,
            self._synonyms,
            self._example_en,
            self._translation,
            self._synonyms_native,
            self._example,
        )
        for lbl in self._labels:
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.NoTextInteraction)
            # Every field here is model output. QLabel auto-detects rich
            # text, so a reply containing markup would be rendered as
            # markup rather than shown literally; pinning the format makes
            # that impossible without needing to escape at each call site.
            lbl.setTextFormat(Qt.PlainText)
        self._pos.setWordWrap(False)  # short tag; wrapping looks broken

        self._divider = QFrame(objectName="divider")
        self._divider.setFixedHeight(1)

        # word + part-of-speech share one row, baseline-ish aligned.
        word_row = QHBoxLayout()
        word_row.setSpacing(8)
        word_row.addWidget(self._word)
        word_row.addWidget(self._pos, alignment=Qt.AlignBottom)
        word_row.addStretch(1)

        # translation + its synonyms share a row the same way - "ಶಾಶ್ವತ
        # (ಕಾಯಂ, ಸ್ಥಿರ)" reads as one headword with its alternatives beside
        # it, rather than a second labelled row underneath.
        translation_row = QHBoxLayout()
        translation_row.setSpacing(8)
        translation_row.addWidget(self._translation)
        translation_row.addWidget(self._synonyms_native, alignment=Qt.AlignBottom)
        translation_row.addStretch(1)

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(4)
        card_layout.addLayout(word_row)
        card_layout.addWidget(self._meaning)
        card_layout.addWidget(self._synonyms)
        card_layout.addWidget(self._example_en)
        card_layout.addWidget(self._divider)
        card_layout.addLayout(translation_row)
        card_layout.addWidget(self._example)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(*([_SHADOW_MARGIN] * 4))
        outer.addWidget(self._card)

        self.setMaximumWidth(460)

        # Outcome dot: not part of card_layout - positioned by hand in the
        # card's own coordinate system so it sits in a corner instead of
        # pushing card content down.
        self._status_dot = QLabel(self._card)
        self._status_dot.setFixedSize(8, 8)
        self._status_dot.raise_()  # above the layout-managed labels below it
        self._status_dot.hide()
        # x isn't set here - the card's width changes with every lookup's
        # content, so top-right has to be recomputed after each resize.
        # See _present().

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    # --- public API (call on GUI thread only) --------------------------

    def show_loading(self, original_hint=""):
        """Instant feedback at the cursor while capture+API run."""
        self._anchor = QCursor.pos()
        self._set_texts(word=original_hint, translation="…")
        self._set_status(None)  # no outcome yet
        self._present(timeout_ms=0)  # no auto-dismiss while loading

    def show_result(self, result: LookupResult):
        self._set_texts(
            word=result.original,
            pos=f"· {result.part_of_speech}" if result.part_of_speech else "",
            meaning=result.meaning,
            synonyms=result.synonyms,
            example_en=result.example_en,
            translation=result.translation,
            # Parenthesized to read as "word (synonym, synonym)" beside the
            # translation, rather than a second bare line under it.
            synonyms_native=f"({result.synonyms_native})" if result.synonyms_native else "",
            example=result.example_native,
        )
        self._set_status("success")
        self._present(timeout_ms=config.POPUP_TIMEOUT_MS)

    def show_message(self, message, timeout_ms=2500, is_error=False):
        """Short status: 'no selection', errors, ON/OFF confirmation.

        is_error marks a genuine lookup failure (red dot). Plain status
        toasts - language switched, shortcuts updated, already running -
        default to no dot: they aren't reporting a lookup outcome, so
        neither red nor green would be an honest signal.
        """
        self._anchor = QCursor.pos()
        self._set_texts(translation=message)
        self._set_status("error" if is_error else None)
        self._present(timeout_ms=timeout_ms)

    # --- internals ------------------------------------------------------

    def _set_texts(self, word="", pos="", meaning="", synonyms="",
                   example_en="", translation="", example="", synonyms_native=""):
        """Fill rows; empty ones collapse. Divider only separates the two
        halves - hidden when the English half has nothing to separate."""
        self._word.setText(word)
        self._pos.setText(pos)
        self._meaning.setText(meaning)
        self._synonyms.setText(synonyms)
        self._example_en.setText(example_en)
        self._translation.setText(translation)
        self._synonyms_native.setText(synonyms_native)
        # Plain text, default leading. A 170% line-height was tried here to
        # stop Indic conjuncts colliding between wrapped lines - but
        # rendering the same sentence at 100/130/140/170% showed they never
        # collided in the first place: default leading is already clear,
        # and 170% simply pushed the lines apart (a 2-line sentence grew
        # 46px -> 79px), which read as uneven spacing against the tighter
        # English rows above. The collision was asserted, not observed.
        self._example.setText(example)
        for lbl in self._labels:
            lbl.setVisible(bool(lbl.text()))
        english_half = bool(meaning or synonyms or example_en)
        native_half = bool(translation or synonyms_native or example)
        self._divider.setVisible(english_half and native_half)

    # (fill colour, corner radius) per state. Radius is half the 8px dot
    # for success (a circle) and a quarter for error (a rounded square),
    # so the two states differ in SHAPE and not only in hue.
    #
    # Colour alone was not enough on two counts, both measured rather than
    # assumed. The previous #00e676 scored 1.49:1 against the card, under
    # the 3:1 WCAG 1.4.11 asks of a non-text indicator - it was pretty and
    # nearly invisible. And red vs green is the commonest colour-vision
    # deficiency: the old pair sat 1.10:1 apart in luminance, so without
    # hue they were the same dot. The replacements measure 3.84:1 (green)
    # and 5.16:1 (red) against the card, but are still only 1.65:1 apart
    # from each other - which is exactly why the shape difference carries
    # the meaning and the colour merely reinforces it.
    _STATUS_STYLES = {
        "success": ("#0E8C4A", 4),
        "error": ("#C5221F", 2),
    }

    def _set_status(self, status):
        """status: "success", "error", or None (hidden)."""
        style = self._STATUS_STYLES.get(status)
        if style is None:
            self._status_dot.hide()
            return
        color, radius = style
        self._status_dot.setStyleSheet(
            f"background: {color}; border-radius: {radius}px;"
        )
        self._status_dot.show()
        self._status_dot.raise_()

    def _present(self, timeout_ms):
        self._timer.stop()
        self.adjustSize()
        # Top-RIGHT, recomputed every call: the card's width changes with
        # each lookup's content, so unlike a fixed top-left offset this
        # can't be set once in __init__.
        #
        # Deliberately NOT self._card.width() here - reproduced directly:
        # right after adjustSize() (and even after show()+processEvents(),
        # in one case) self._card.width() and self._card.sizeHint().width()
        # both still returned a stale/wrong value, while self.width() (the
        # top-level popup adjustSize() just resized) was immediately correct
        # and stayed correct. self._card fills self exactly except for the
        # outer layout's _SHADOW_MARGIN on each side, so subtracting that
        # twice gives the card's real width without needing self._card's
        # own geometry to have caught up yet.
        card_width = self.width() - 2 * _SHADOW_MARGIN
        self._status_dot.move(card_width - 8 - self._status_dot.width(), 8)
        self.move(self._clamped(getattr(self, "_anchor", QCursor.pos())))
        self.show()
        if timeout_ms:
            self._timer.start(timeout_ms)

    def _clamped(self, anchor: QPoint) -> QPoint:
        """Offset from cursor, kept fully on the cursor's screen. The
        shadow margin is transparent window space - subtract it so the
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
