"""Capture the currently selected text in ANY app via a clipboard round-trip.

Why clipboard: no OS offers a universal "give me the selected text" API
across arbitrary apps (UI Automation fails in PDF viewers and Electron
apps). Simulating the copy shortcut works everywhere, so:

  1. snapshot current clipboard text
  2. send a synthetic copy chord (Ctrl+C / Cmd+C — platform backend)
  3. wait for the clipboard "change token" to move — on Windows that's
     the exact clipboard sequence number; on mac/linux it's a content
     compare (see platforms/)
  4. read the copied selection
  5. restore the snapshot so the user's clipboard is untouched

Limitation (documented, accepted): snapshot/restore is text-only. If the
clipboard held an image or file list, that content is lost by the
round-trip — restoring every exotic clipboard format is out of scope.
"""

import time

from . import config
from .platforms import backend

# How long to wait for the target app to service our copy chord.
_COPY_WAIT_S = 0.6
_POLL_S = 0.02


def grab_selection():
    """Return the currently selected text, or None if nothing was selected.

    Runs on a worker thread (never the GUI thread) — it sleeps while
    polling for the copy to land.
    """
    original = backend.read_text()
    token_before = backend.change_token()

    backend.send_copy()

    # Wait for the token to move — proof the target app actually wrote
    # something. Apps with nothing selected typically ignore the copy
    # chord entirely, so the token never changes.
    deadline = time.monotonic() + _COPY_WAIT_S
    changed = False
    while time.monotonic() < deadline:
        if backend.change_token() != token_before:
            changed = True
            break
        time.sleep(_POLL_S)

    if not changed:
        return None

    selection = backend.read_text()

    # Restore the user's clipboard (text-only, see module docstring).
    backend.write_text(original)

    if not selection or not selection.strip():
        return None

    text = " ".join(selection.split())  # collapse newlines from PDF line-wraps
    if len(text) > config.MAX_CHARS:
        # Truncate at a word boundary to cap API spend on huge selections.
        text = text[: config.MAX_CHARS].rsplit(" ", 1)[0]
    return text
