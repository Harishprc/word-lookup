"""Unit tests for the clipboard round-trip — no real clipboard, no OS
backend. A fake backend stands in for platforms/{win,mac,linux}.py so both
change-detection strategies can be exercised on any machine:

  TOKEN_IS_CONTENT=False (Windows) — change_token() is a monotonic
      sequence number that moves on ANY clipboard write.
  TOKEN_IS_CONTENT=True  (mac/linux) — change_token() IS the content, so
      an unchanged token is ambiguous between "copied identical text" and
      "copied nothing". capture.grab_selection resolves that with a
      sentinel probe; the leak tests below are what keep it honest.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kannada_lookup import capture  # noqa: E402


class FakeBackend:
    """Scriptable clipboard. `copies` is what the "focused app" writes when
    it receives the copy chord — None means nothing is selected, so the
    chord is a no-op (exactly how a real app behaves)."""

    def __init__(self, clipboard=None, copies=None, token_is_content=False):
        self.clipboard = clipboard
        self.copies = copies
        self.TOKEN_IS_CONTENT = token_is_content
        self._seq = 0
        self.copy_calls = 0

    def read_text(self):
        return self.clipboard

    def write_text(self, text):
        if text is None:  # matches the real backends' None guard
            return
        self.clipboard = text
        self._seq += 1

    def change_token(self):
        return self.clipboard if self.TOKEN_IS_CONTENT else self._seq

    def send_copy(self, release_vks=()):
        self.copy_calls += 1
        if self.copies is not None:
            self.write_text(self.copies)


@pytest.fixture
def fast_poll(monkeypatch):
    """Don't burn 0.6s of wall clock per no-copy test."""
    monkeypatch.setattr(capture, "_COPY_WAIT_S", 0.01)
    monkeypatch.setattr(capture, "_POLL_S", 0.001)


def _run(monkeypatch, backend):
    monkeypatch.setattr(capture, "backend", backend)
    return capture.grab_selection()


# --- the leak this suite exists for -------------------------------------------


def test_no_selection_does_not_leak_clipboard_on_content_compare(monkeypatch, fast_poll):
    """THE regression test: on mac/linux, triggering a lookup with nothing
    selected must return None — NOT the user's pre-existing clipboard.
    Returning it would ship whatever was copied last (a password, a private
    note) to the translation API and into the local cache."""
    backend = FakeBackend(
        clipboard="password: hunter2", copies=None, token_is_content=True
    )
    assert _run(monkeypatch, backend) is None


def test_no_selection_restores_clipboard_after_probing(monkeypatch, fast_poll):
    """The sentinel we write to disambiguate must never be left behind."""
    backend = FakeBackend(
        clipboard="password: hunter2", copies=None, token_is_content=True
    )
    _run(monkeypatch, backend)
    assert backend.clipboard == "password: hunter2"


def test_no_selection_returns_none_on_sequence_number_platform(monkeypatch, fast_poll):
    """Windows has no ambiguity to resolve — same outcome, simpler path."""
    backend = FakeBackend(clipboard="password: hunter2", copies=None)
    assert _run(monkeypatch, backend) is None
    assert backend.clipboard == "password: hunter2"


def test_selection_identical_to_clipboard_still_works(monkeypatch, fast_poll):
    """The case the sentinel probe exists to preserve: re-selecting text
    that already happens to be on the clipboard is a real lookup, not a
    no-op, even though the content never changes."""
    backend = FakeBackend(clipboard="ephemeral", copies="ephemeral", token_is_content=True)
    assert _run(monkeypatch, backend) == "ephemeral"
    assert backend.clipboard == "ephemeral"  # restored


# --- ordinary round trip -------------------------------------------------------


@pytest.mark.parametrize("token_is_content", [True, False])
def test_selection_returned_and_clipboard_restored(monkeypatch, fast_poll, token_is_content):
    backend = FakeBackend(
        clipboard="previous contents",
        copies="serendipity",
        token_is_content=token_is_content,
    )
    assert _run(monkeypatch, backend) == "serendipity"
    assert backend.clipboard == "previous contents"


def test_empty_clipboard_and_no_selection(monkeypatch, fast_poll):
    backend = FakeBackend(clipboard=None, copies=None, token_is_content=True)
    assert _run(monkeypatch, backend) is None


def test_whitespace_only_selection_rejected(monkeypatch, fast_poll):
    backend = FakeBackend(clipboard="x", copies="   \n  ", token_is_content=True)
    assert _run(monkeypatch, backend) is None


def test_newlines_collapsed(monkeypatch, fast_poll):
    """PDF line-wraps arrive as embedded newlines."""
    backend = FakeBackend(clipboard="x", copies="hello\n  world\ttoo")
    assert _run(monkeypatch, backend) == "hello world too"


def test_long_selection_truncated_at_word_boundary(monkeypatch, fast_poll):
    backend = FakeBackend(clipboard="x", copies="word " * 200)
    result = _run(monkeypatch, backend)
    assert len(result) <= capture.config.MAX_CHARS
    assert not result.endswith("wor")  # cut at a space, not mid-word


# --- secret screening ----------------------------------------------------------


def test_secret_shaped_selection_never_leaves_the_machine(monkeypatch, fast_poll):
    backend = FakeBackend(clipboard="x", copies="sk-proj-8fQ2xM9pKz4bTn7rE1yW6h")
    assert _run(monkeypatch, backend) is None


def test_docstring_examples_are_actually_caught():
    """_looks_like_secret's docstring cites these — if they don't trip the
    check, the docstring is lying to the next reader."""
    assert capture._looks_like_secret("sk-proj-8fQ2xM9pKz4bTn7rE1yW6h")
    assert capture._looks_like_secret("Tr0ub4dor&3xyz9!AbCd")


def test_ordinary_words_are_not_screened_as_secrets():
    for word in ("ephemeral", "serendipity", "how are you", "Weltschmerz"):
        assert not capture._looks_like_secret(word)


def test_long_lowercase_word_is_not_a_secret():
    """Only 1 character class — a long word must still look up fine."""
    assert not capture._looks_like_secret("pneumonoultramicroscopicsilicovolcanoconiosis")
