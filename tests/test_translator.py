"""Unit tests — HTTP mocked, no key/network needed."""

import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kannada_lookup import register  # noqa: E402
from kannada_lookup.store import LookupStore  # noqa: E402
from kannada_lookup.translator import (  # noqa: E402
    CachedProvider,
    GeminiProvider,
    GoogleTranslateProvider,
    LookupFailed,
    LookupResult,
    TranslationProvider,
    make_provider,
)


def _response(status=200, payload=None):
    resp = MagicMock()
    resp.status_code = status
    resp.ok = status == 200
    resp.json.return_value = payload or {}
    return resp


def _gemini_payload(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


# --- GoogleTranslateProvider (legacy) --------------------------------------


def test_google_lookup_parses_and_unescapes():
    payload = {"data": {"translations": [{"translatedText": "ಶಾಲೆ &amp; ಮನೆ"}]}}
    with patch("kannada_lookup.translator.requests.post", return_value=_response(200, payload)) as post:
        result = GoogleTranslateProvider("k").lookup("school & home")
    assert result.translation == "ಶಾಲೆ & ಮನೆ"  # HTML entity unescaped
    assert result.original == "school & home"
    assert post.call_args.kwargs["data"]["target"] == "kn"


def test_google_bad_key_is_presentable_error():
    with patch("kannada_lookup.translator.requests.post", return_value=_response(403)):
        with pytest.raises(LookupFailed, match="403"):
            GoogleTranslateProvider("bad").lookup("word")


def test_google_missing_key_raises():
    with pytest.raises(LookupFailed, match="API key"):
        GoogleTranslateProvider("")


def test_google_malformed_response():
    with patch("kannada_lookup.translator.requests.post", return_value=_response(200, {"nope": 1})):
        with pytest.raises(LookupFailed, match="response format"):
            GoogleTranslateProvider("k").lookup("word")


def test_factory_rejects_unknown_provider(monkeypatch):
    monkeypatch.setattr("kannada_lookup.config.PROVIDER", "llamacorn")
    with pytest.raises(LookupFailed, match="llamacorn"):
        make_provider()


# --- GeminiProvider ---------------------------------------------------------


_FULL_JSON = (
    '{"part_of_speech": "noun", '
    '"meaning": "physical power or energy", '
    '"synonyms": ["power", "might", "force"], '
    '"example_en": "She has the strength to lift it.", '
    '"translation": "ಶಕ್ತಿ", '
    '"example_native": "ಅವನಿಗೆ ತುಂಬಾ ಶಕ್ತಿ ಇದೆ."}'
)


def test_gemini_happy_path_full_card():
    with patch(
        "kannada_lookup.translator.requests.post",
        return_value=_response(200, _gemini_payload(_FULL_JSON)),
    ) as post:
        result = GeminiProvider("k", "m", "Kannada").lookup("strength")
    assert result.translation == "ಶಕ್ತಿ"
    assert result.part_of_speech == "noun"
    assert result.meaning == "physical power or energy"
    assert result.synonyms == "power, might, force"  # list joined
    assert result.example_en == "She has the strength to lift it."
    assert result.example_native == "ಅವನಿಗೆ ತುಂಬಾ ಶಕ್ತಿ ಇದೆ."
    assert result.original == "strength"
    body = post.call_args.kwargs["json"]
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    prompt = body["contents"][0]["parts"][0]["text"]
    assert "strength" in prompt
    assert "part_of_speech" in prompt


def test_gemini_prompt_uses_configured_language():
    # Devanagari payload: this asks for Hindi, so a Kannada reply would now
    # (correctly) be rejected by the script check and retried.
    hindi_json = '{"translation": "शक्ति", "meaning": "physical power"}'
    with patch(
        "kannada_lookup.translator.requests.post",
        return_value=_response(200, _gemini_payload(hindi_json)),
    ) as post:
        GeminiProvider("k", "m", "Hindi").lookup("strength")
    prompt = post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
    assert "English-Hindi dictionary" in prompt
    assert "Hindi translation" in prompt
    assert "Kannada" not in prompt


def test_gemini_prompt_forbids_the_known_bad_output_shapes():
    """Weak models invent words in low-resource scripts (Kannada
    "restricted" once returned "ಮಿಚ್ಛಿತ / ನಿಯನ್ಶ್ರಿತ" — two non-words, the
    second a malformed cluster). These constraints are what suppress that,
    so they must not be dropped."""
    with patch(
        "kannada_lookup.translator.requests.post",
        return_value=_response(200, _gemini_payload(_FULL_JSON)),
    ) as post:
        GeminiProvider("k", "m", "Kannada").lookup("restricted")
    prompt = post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
    assert "exactly ONE translation" in prompt
    assert "never use a slash" in prompt
    assert "real, standard Kannada word" in prompt
    assert "phonetically" in prompt
    assert "malformed clusters" in prompt


def _kannada_json(translation):
    return (
        '{"translation": "%s", "meaning": "the act of holding back", '
        '"example_native": "ಸತ್ಯದ ದಮನ ತಪ್ಪು."}' % translation
    )


def test_gemini_retries_once_when_the_reply_is_in_the_wrong_script():
    """The real failure: asking for Kannada and getting Devanagari — right
    word, wrong alphabet, unreadable to the user. First reply is rejected,
    the retry succeeds, and only the good one is returned."""
    replies = [
        _response(200, _gemini_payload(_kannada_json("दमन"))),    # Devanagari
        _response(200, _gemini_payload(_kannada_json("ದಮನ"))),    # Kannada
    ]
    with patch(
        "kannada_lookup.translator.requests.post", side_effect=replies
    ) as post:
        result = GeminiProvider("k", "m", "Kannada").lookup("suppression")
    assert result.translation == "ದಮನ"
    assert post.call_count == 2
    # The retry must name the mistake, not just repeat the original prompt.
    retry_prompt = post.call_args_list[1].kwargs["json"]["contents"][0]["parts"][0]["text"]
    assert "wrong alphabet" in retry_prompt
    assert "Kannada script" in retry_prompt


def test_gemini_does_not_retry_when_the_script_is_already_correct():
    """The retry costs an extra API call, so it must only fire on failure."""
    with patch(
        "kannada_lookup.translator.requests.post",
        return_value=_response(200, _gemini_payload(_kannada_json("ದಮನ"))),
    ) as post:
        GeminiProvider("k", "m", "Kannada").lookup("suppression")
    assert post.call_count == 1


def test_gemini_raises_when_the_script_is_wrong_twice():
    """Failing loudly keeps the bad answer out of the cache, which is keyed
    by word with no model in the key — a stored wrong-script row would be
    served forever."""
    bad = _response(200, _gemini_payload(_kannada_json("दमन")))
    with patch("kannada_lookup.translator.requests.post", side_effect=[bad, bad]):
        with pytest.raises(LookupFailed, match="wrong script"):
            GeminiProvider("k", "m", "Kannada").lookup("suppression")


def test_gemini_latin_target_never_triggers_the_script_retry():
    """Swedish shares the ASCII range with English, so there is nothing to
    check — a Latin answer must not be mistaken for a wrong-script reply."""
    payload = _response(
        200, _gemini_payload('{"translation": "svar", "meaning": "a reply"}')
    )
    with patch(
        "kannada_lookup.translator.requests.post", return_value=payload
    ) as post:
        result = GeminiProvider("k", "m", "Swedish").lookup("response")
    assert result.translation == "svar"
    assert post.call_count == 1


def test_gemini_strips_markdown_fences():
    raw = '```json\n{"translation": "ಪುಸ್ತಕ", "example_native": "ಇದು ನನ್ನ ಪುಸ್ತಕ."}\n```'
    with patch(
        "kannada_lookup.translator.requests.post",
        return_value=_response(200, _gemini_payload(raw)),
    ):
        result = GeminiProvider("k", "m", "Kannada").lookup("book")
    assert result.translation == "ಪುಸ್ತಕ"
    assert result.example_native == "ಇದು ನನ್ನ ಪುಸ್ತಕ."


def test_gemini_optional_fields_tolerated():
    raw = '{"translation": "ಹೇಗಿದ್ದೀರಾ", "synonyms": "howdy, hiya"}'
    with patch(
        "kannada_lookup.translator.requests.post",
        return_value=_response(200, _gemini_payload(raw)),
    ):
        result = GeminiProvider("k", "m", "Kannada").lookup("how are you")
    assert result.translation == "ಹೇಗಿದ್ದೀರಾ"
    assert result.synonyms == "howdy, hiya"
    assert result.part_of_speech == ""
    assert result.meaning == ""
    assert result.example_en == ""


def test_gemini_bad_key():
    with patch("kannada_lookup.translator.requests.post", return_value=_response(400)):
        with pytest.raises(LookupFailed, match="GEMINI_API_KEY"):
            GeminiProvider("bad", "m", "Kannada").lookup("word")


def test_gemini_quota_exhausted():
    with patch("kannada_lookup.translator.requests.post", return_value=_response(429)):
        with pytest.raises(LookupFailed, match="quota"):
            GeminiProvider("k", "m", "Kannada").lookup("word")


def test_gemini_unknown_model_names_fix():
    with patch("kannada_lookup.translator.requests.post", return_value=_response(404)):
        with pytest.raises(LookupFailed, match="GEMINI_MODEL"):
            GeminiProvider("k", "m", "Kannada").lookup("word")


def test_gemini_missing_key_raises():
    with pytest.raises(LookupFailed, match="aistudio"):
        GeminiProvider("", "m", "Kannada")


def test_gemini_unparseable_reply():
    with patch(
        "kannada_lookup.translator.requests.post",
        return_value=_response(200, _gemini_payload("sorry, no JSON today")),
    ):
        with pytest.raises(LookupFailed, match="model reply"):
            GeminiProvider("k", "m", "Kannada").lookup("word")


# --- offline store & caching ------------------------------------------------


_RESULT = LookupResult(
    original="Strength",
    translation="ಶಕ್ತಿ",
    part_of_speech="noun",
    meaning="physical power",
    synonyms="power, might",
    example_en="She has great strength.",
    example_native="ಅವನಿಗೆ ಶಕ್ತಿ ಇದೆ.",
)


class _FakeProvider(TranslationProvider):
    """Scriptable inner provider: counts calls, can be told to fail."""

    def __init__(self, result=_RESULT, fail_with=None):
        self.calls = 0
        self._result = result
        self._fail_with = fail_with

    def lookup(self, text):
        self.calls += 1
        if self._fail_with:
            raise LookupFailed(self._fail_with)
        return self._result


@pytest.fixture
def kannada_lang(monkeypatch):
    monkeypatch.setattr("kannada_lookup.config.TARGET_LANGUAGE", "Kannada")


def test_store_roundtrip_and_normalization(tmp_path):
    store = LookupStore(tmp_path / "t.db")
    store.put(_RESULT, "Kannada", provider="test")
    got = store.get("  strength ", "Kannada")  # key normalized
    assert got == _RESULT
    assert store.get("unseen-word", "Kannada") is None
    # Per-language keying: same word, other language = miss.
    assert store.get("strength", "Hindi") is None


def test_store_migrates_v1_rows(tmp_path):
    """Pre-multi-language DBs carry their rows over as Kannada."""
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE lookups (key TEXT PRIMARY KEY, original TEXT, "
            "kannada TEXT, meaning TEXT DEFAULT '', synonyms TEXT DEFAULT '', "
            "example TEXT DEFAULT '', provider TEXT DEFAULT '', created_at REAL)"
        )
        con.execute(
            "INSERT INTO lookups VALUES ('strength', 'Strength', 'ಶಕ್ತಿ', "
            "'physical power', 'power, might', 'ಅವನಿಗೆ ಶಕ್ತಿ ಇದೆ.', 'g', 1.0)"
        )
    store = LookupStore(db)
    got = store.get("strength", "Kannada")
    assert got is not None
    assert got.translation == "ಶಕ್ತಿ"
    assert got.example_native == "ಅವನಿಗೆ ಶಕ್ತಿ ಇದೆ."
    assert got.example_en == ""  # column didn't exist in v1
    with sqlite3.connect(db) as con:
        assert con.execute(
            "SELECT name FROM sqlite_master WHERE name='lookups'"
        ).fetchone() is None  # old table dropped


def test_cached_provider_miss_then_hit(tmp_path, kannada_lang):
    inner = _FakeProvider()
    p = CachedProvider(inner, LookupStore(tmp_path / "t.db"))
    first = p.lookup("Strength")
    second = p.lookup("strength")  # different case — same cache entry
    assert first == second == _RESULT
    assert inner.calls == 1  # API touched exactly once


def test_cached_word_survives_offline(tmp_path, kannada_lang):
    store = LookupStore(tmp_path / "t.db")
    CachedProvider(_FakeProvider(), store).lookup("strength")  # cache it
    offline = CachedProvider(_FakeProvider(fail_with="No internet"), store)
    assert offline.lookup("strength") == _RESULT


def test_uncached_word_offline_still_fails(tmp_path, kannada_lang):
    p = CachedProvider(
        _FakeProvider(fail_with="No internet"), LookupStore(tmp_path / "t.db")
    )
    with pytest.raises(LookupFailed, match="No internet"):
        p.lookup("never-seen")


def test_failed_lookup_not_cached(tmp_path, kannada_lang):
    store = LookupStore(tmp_path / "t.db")
    failing = CachedProvider(_FakeProvider(fail_with="boom"), store)
    with pytest.raises(LookupFailed):
        failing.lookup("word")
    assert store.get("word", "Kannada") is None


def _patched_store(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "kannada_lookup.store.LookupStore",
        lambda *a, **k: LookupStore(tmp_path / "t.db"),
    )


def test_factory_selects_gemini_wrapped_in_cache(monkeypatch, tmp_path):
    monkeypatch.setattr("kannada_lookup.config.PROVIDER", "gemini")
    monkeypatch.setattr("kannada_lookup.config.GEMINI_API_KEY", "k")
    _patched_store(monkeypatch, tmp_path)
    p = make_provider()
    assert isinstance(p, CachedProvider)
    assert isinstance(p._inner, GeminiProvider)


def test_factory_still_selects_google(monkeypatch, tmp_path):
    monkeypatch.setattr("kannada_lookup.config.PROVIDER", "google")
    monkeypatch.setattr("kannada_lookup.config.GOOGLE_API_KEY", "k")
    _patched_store(monkeypatch, tmp_path)
    p = make_provider()
    assert isinstance(p, CachedProvider)
    assert isinstance(p._inner, GoogleTranslateProvider)


# --- HTML register ------------------------------------------------------------


def test_register_generation(tmp_path):
    store = LookupStore(tmp_path / "t.db")
    store.put(_RESULT, "Kannada", provider="test")
    out = register.generate(store, out_path=tmp_path / "register.html")
    page = out.read_text(encoding="utf-8")
    assert "Strength" in page
    assert "ಶಕ್ತಿ" in page
    assert "She has great strength." in page
    assert "power, might" in page
    assert "noun" in page
    assert 'id="search"' in page  # search box present
    assert "1 lookups" in page


def test_register_reflects_a_lookup_added_after_the_first_generation(tmp_path):
    """The reported bug was "register not updating after lookups". The file
    itself was always correct — the browser was re-serving a cached copy of
    an unchanging file:// URL — but pin the regeneration behaviour anyway,
    since that is the half this module is responsible for."""
    store = LookupStore(tmp_path / "t.db")
    out = tmp_path / "r.html"

    store.put(_RESULT, "Kannada", provider="test")
    first = register.generate(store, out_path=out).read_text(encoding="utf-8")
    assert "1 lookups" in first
    assert "Serendipity" not in first

    store.put(
        LookupResult(original="Serendipity", translation="ಆಕಸ್ಮಿಕ"),
        "Kannada",
        provider="test",
    )
    second = register.generate(store, out_path=out).read_text(encoding="utf-8")
    assert "2 lookups" in second
    assert "Serendipity" in second
    assert "Strength" in second  # the earlier one survives


def test_register_lists_newest_first(tmp_path):
    """Newest-first is what makes the page useful right after a lookup; if
    this flipped, a new word would land at the bottom of a long table and
    look like nothing had happened.

    Indices are compared inside <tbody> only: the page chrome contains the
    search box's `placeholder=`, and a naive page.index("older") matches
    the "older" inside *that* word, before any row.
    """
    store = LookupStore(tmp_path / "t.db")
    store.put(LookupResult(original="older", translation="ಹಳೆಯ"), "Kannada")
    store.put(LookupResult(original="newer", translation="ಹೊಸ"), "Kannada")
    page = register.generate(store, out_path=tmp_path / "r.html").read_text(
        encoding="utf-8"
    )
    body = page.split('<tbody id="rows">', 1)[1].split("</tbody>", 1)[0]
    assert body.index("newer") < body.index("older")


def test_register_page_forbids_caching(tmp_path):
    """Without this a manual reload or bookmark (neither carries the
    cache-busting query main.py appends) can still show a stale page."""
    page = register.generate(
        LookupStore(tmp_path / "t.db"), out_path=tmp_path / "r.html"
    ).read_text(encoding="utf-8")
    assert "no-store" in page


def test_register_default_path_is_unique_per_call(tmp_path, monkeypatch):
    """The actual bug: Windows resolves a file:// URL for a locally-
    associated .html extension through the file-type handler, which
    launches the browser as `browser.exe --single-argument <path>` —
    the URL wrapper is dropped, query string included. A constant
    filename was therefore byte-identical on every open regardless of
    any URL trick, and the browser kept its cached render. Only a path
    that changes on every generate() survives that hop, which is why
    the filename itself must carry the uniqueness."""
    monkeypatch.setattr(register, "OUT_DIR", tmp_path)
    store = LookupStore(tmp_path / "t.db")
    store.put(_RESULT, "Kannada", provider="test")

    first = register.generate(store)
    second = register.generate(store)

    assert first != second
    assert first.name.startswith("register-") and first.name.endswith(".html")
    assert second.exists()


def test_register_cleans_up_earlier_files(tmp_path, monkeypatch):
    """Without cleanup, every "Open word register" click would leave a new
    file behind forever."""
    monkeypatch.setattr(register, "OUT_DIR", tmp_path)
    store = LookupStore(tmp_path / "t.db")
    store.put(_RESULT, "Kannada", provider="test")

    first = register.generate(store)
    assert first.exists()
    second = register.generate(store)

    assert not first.exists()
    assert second.exists()
    assert list(tmp_path.glob("register-*.html")) == [second]


def test_register_cleanup_ignores_a_locked_file(tmp_path, monkeypatch):
    """A previous register page can still be open in a browser tab, which
    can hold the file locked on Windows. That must not crash the next
    "Open word register" click — the old file is just left for next time."""
    monkeypatch.setattr(register, "OUT_DIR", tmp_path)
    store = LookupStore(tmp_path / "t.db")
    store.put(_RESULT, "Kannada", provider="test")
    first = register.generate(store)

    real_unlink = Path.unlink

    def locked_unlink(self, *a, **kw):
        if self == first:
            raise OSError("file in use")
        return real_unlink(self, *a, **kw)

    monkeypatch.setattr(Path, "unlink", locked_unlink)
    second = register.generate(store)  # must not raise
    assert second.exists()


def test_register_empty_store(tmp_path):
    out = register.generate(
        LookupStore(tmp_path / "t.db"), out_path=tmp_path / "r.html"
    )
    assert "No lookups yet" in out.read_text(encoding="utf-8")


def test_register_escapes_html(tmp_path):
    store = LookupStore(tmp_path / "t.db")
    store.put(
        LookupResult(original="<script>x</script>", translation="ಇ"),
        "Kannada",
    )
    page = register.generate(store, out_path=tmp_path / "r.html").read_text(
        encoding="utf-8"
    )
    assert "<script>x</script>" not in page
    assert "&lt;script&gt;" in page


# --- settings / first-run -----------------------------------------------------


def test_settings_roundtrip(monkeypatch, tmp_path):
    from kannada_lookup import config

    monkeypatch.setattr(config, "SETTINGS_PATH", tmp_path / "settings.json")
    try:
        assert config.load_settings() is None  # first run
        config.save_settings("Hindi")
        assert config.load_settings() == {"target_language": "Hindi"}
        assert config.TARGET_LANGUAGE == "Hindi"
        assert config.TARGET_LANG == "hi"
        assert config.LANGUAGE_GLYPH == "अ"
    finally:
        # save_settings mutates module globals — restore from the real
        # settings file so later tests aren't polluted.
        monkeypatch.undo()
        config.refresh_language()
