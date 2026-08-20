"""Capture the currently selected text in ANY app via a clipboard round-trip.

Why clipboard: no OS offers a universal "give me the selected text" API
across arbitrary apps (UI Automation fails in PDF viewers and Electron
apps). Simulating the copy shortcut works everywhere, so:

  1. snapshot current clipboard text
  2. send a synthetic copy chord (Ctrl+C / Cmd+C - platform backend)
  3. wait for the clipboard "change token" to move - on Windows that's
     the exact clipboard sequence number; on mac/linux it's a content
     compare (see platforms/)
  4. read the copied selection
  5. restore the snapshot so the user's clipboard is untouched

Limitation (documented, accepted): snapshot/restore is text-only. If the
clipboard held an image or file list, that content is lost by the
round-trip - restoring every exotic clipboard format is out of scope.
"""

import time

from . import config
from .platforms import backend

# How long to wait for the target app to service our copy chord.
_COPY_WAIT_S = 0.6
_POLL_S = 0.02

# Below this length a token is assumed to be a word/phrase, never a secret
# - real passwords, API keys and tokens worth blocking are long. Kept
# short so ordinary lookups are never affected.
_SECRET_LIKE_MIN_LEN = 20

# Written to the clipboard before the copy chord on content-compare
# platforms, so "the app copied nothing" is distinguishable from "the app
# copied text identical to what was already there". Deliberately something
# no real selection could ever be. See grab_selection.
_PROBE_SENTINEL = "\x00word-lookup-probe\x00"


def _looks_like_secret(text: str) -> bool:
    """True for a single unspaced token that mixes enough character classes
    to look like a generated password/API key/token rather than a word or
    phrase - e.g. "sk-proj-8fQ2xM9pKz4bTn7rE1yW6h", "Tr0ub4dor&3xyz9!AbCd".
    (Both examples clear _SECRET_LIKE_MIN_LEN; anything shorter is rejected
    by the length guard before the character-class test runs at all.)
    Deliberately conservative: real lookups are short and/or contain
    spaces, so this only ever screens out things that were never going to
    be a dictionary lookup in the first place."""
    if " " in text or len(text) < _SECRET_LIKE_MIN_LEN:
        return False
    classes = sum((
        any(c.islower() for c in text),
        any(c.isupper() for c in text),
        any(c.isdigit() for c in text),
        any(not c.isalnum() for c in text),
    ))
    return classes >= 3


def grab_selection(release_vks=()):
    """Return the currently selected text, or None if nothing was selected.

    Runs on a worker thread (never the GUI thread) - it sleeps while
    polling for the copy to land.

    `release_vks` are keys the user is still physically holding because
    they triggered this with a keyboard shortcut; the backend releases
    them before sending the copy chord so it isn't polluted. The mouse
    path passes nothing.
    """
    original = backend.read_text()

    # On platforms where change_token() is a content compare (mac, linux -
    # Windows uses the exact clipboard sequence number instead), "the app
    # copied a selection identical to what was already on the clipboard"
    # and "the app copied nothing at all" are indistinguishable: the token
    # sits still either way. Prime the clipboard with a sentinel so they
    # separate cleanly - any value other than the sentinel afterwards is
    # proof a real copy landed.
    #
    # This must never degrade into "assume the copy worked": a trigger with
    # nothing selected would then read the user's pre-existing clipboard
    # back out and ship it to the translation API and the local cache.
    #
    # Only primed when there is actually something to protect: an empty or
    # unreadable clipboard has no ambiguity to resolve (nothing copied
    # reads back as nothing, which the empty-selection check below already
    # rejects) and no content worth restoring.
    probing = getattr(backend, "TOKEN_IS_CONTENT", False) and bool(original)
    if probing:
        backend.write_text(_PROBE_SENTINEL)

    token_before = backend.change_token()

    backend.send_copy(release_vks)

    # Wait for the token to move - proof the target app actually wrote
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
        # Nothing was copied. Put back what we displaced to probe.
        if probing:
            backend.write_text(original)
        return None

    selection = backend.read_text()

    # Restore the user's clipboard (text-only, see module docstring).
    backend.write_text(original)

    if not selection or not selection.strip():
        return None

    text = " ".join(selection.split())  # collapse newlines from PDF line-wraps
    if _looks_like_secret(text):
        # Never send a password/API-key-shaped token to the lookup API or
        # cache it - see _looks_like_secret.
        return None
    if len(text) > config.MAX_CHARS:
        # Truncate at a word boundary to cap API spend on huge selections.
        text = text[: config.MAX_CHARS].rsplit(" ", 1)[0]
    return text
