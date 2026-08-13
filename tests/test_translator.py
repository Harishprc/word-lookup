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
    '"synonyms_native": ["ಬಲ", "ಸಾಮರ್ಥ್ಯ"], '
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


def test_gemini_parses_native_synonyms():
    with patch(
        "kannada_lookup.translator.requests.post",
        return_value=_response(200, _gemini_payload(_FULL_JSON)),
    ) as post:
        result = GeminiProvider("k", "m", "Kannada").lookup("strength")
    assert result.synonyms_native == "ಬಲ, ಸಾಮರ್ಥ್ಯ"  # list joined
    assert result.synonyms == "power, might, force"  # English half untouched
    prompt = post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
    assert "synonyms_native" in prompt


def test_gemini_native_synonyms_accept_a_plain_string():
    """Same list-or-string tolerance the English synonyms field has had."""
    raw = '{"translation": "ಶಕ್ತಿ", "synonyms_native": "ಬಲ, ಸಾಮರ್ಥ್ಯ"}'
    with patch(
        "kannada_lookup.translator.requests.post",
        return_value=_response(200, _gemini_payload(raw)),
    ):
        result = GeminiProvider("k", "m", "Kannada").lookup("strength")
    assert result.synonyms_native == "ಬಲ, ಸಾಮರ್ಥ್ಯ"


def test_gemini_native_synonyms_drop_the_translation_itself():
    """Models sometimes echo the translation back as its own synonym,
    which renders as a duplicate directly under it on the card."""
    raw = (
        '{"translation": "ಶಕ್ತಿ", '
        '"synonyms_native": ["ಶಕ್ತಿ", "ಬಲ"]}'
    )
    with patch(
        "kannada_lookup.translator.requests.post",
        return_value=_response(200, _gemini_payload(raw)),
    ):
        result = GeminiProvider("k", "m", "Kannada").lookup("strength")
    assert result.synonyms_native == "ಬಲ"


def test_gemini_missing_native_synonyms_is_not_an_error():
    """Older providers and multi-word phrases legitimately omit it; the
    card hides the row rather than failing the lookup."""
    raw = '{"translation": "ಶಕ್ತಿ", "meaning": "power"}'
    with patch(
        "kannada_lookup.translator.requests.post",
        return_value=_response(200, _gemini_payload(raw)),
    ):
        result = GeminiProvider("k", "m", "Kannada").lookup("strength")
    assert result.synonyms_native == ""


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


def test_gemini_retries_a_mixed_script_reply_too():
    """The other real failure, from flash-lite against the live API:
    "कृतज्ञತೆ" for Kannada — four Devanagari characters and one real
    Kannada one. Not zero correct characters like the other test, so this
    exercises the "no foreign characters" half of the check separately
    from the "has own characters" half."""
    replies = [
        _response(200, _gemini_payload(_kannada_json("कृतज्ञತೆ"))),  # mixed
        _response(200, _gemini_payload(_kannada_json("ಕೃತಜ್ಞತೆ"))),  # pure Kannada
    ]
    with patch("kannada_lookup.translator.requests.post", side_effect=replies) as post:
        result = GeminiProvider("k", "m", "Kannada").lookup("gratitude")
    assert result.translation == "ಕೃತಜ್ಞತೆ"
    assert post.call_count == 2


def test_gemini_does_not_retry_when_the_script_is_already_correct():
    """The retry costs an extra API call, so it must only fire on failure."""
    with patch(
        "kannada_lookup.translator.requests.post",
        return_value=_response(200, _gemini_payload(_kannada_json("ದಮನ"))),
    ) as post:
        GeminiProvider("k", "m", "Kannada").lookup("suppression")
    assert post.call_count == 1


def test_retry_keeps_english_fields_when_the_model_returns_a_sparse_reply():
    """The real bug: asked to "reply again in Kannada script", the model
    treats the translation as the whole task and returns a stripped
    object. Observed live for "configuration" — the retry dropped
    example_native, and the empty value got cached, so the card showed no
    native example sentence."""
    first = _response(200, _gemini_payload(
        '{"translation": "दमन", "meaning": "the act of holding back", '
        '"synonyms": "repression, restraint", '
        '"example_en": "The suppression of dissent.", '
        '"part_of_speech": "noun", '
        '"example_native": "दमन का उदाहरण।"}'
    ))
    # Retry: right script, but everything else stripped out.
    sparse_retry = _response(200, _gemini_payload('{"translation": "ದಮನ"}'))

    with patch(
        "kannada_lookup.translator.requests.post", side_effect=[first, sparse_retry]
    ):
        result = GeminiProvider("k", "m", "Kannada").lookup("suppression")

    assert result.translation == "ದಮನ"          # corrected script kept
    assert result.meaning == "the act of holding back"   # English recovered
    assert result.synonyms == "repression, restraint"
    assert result.example_en == "The suppression of dissent."
    assert result.part_of_speech == "noun"


def test_retry_never_carries_over_the_rejected_native_fields():
    """The earlier reply was rejected for being in the wrong script, so
    its native-language fields are precisely the ones that must NOT be
    reused — otherwise the fix would reintroduce the Devanagari it just
    rejected."""
    first = _response(200, _gemini_payload(
        '{"translation": "दमन", "example_native": "दमन का उदाहरण।", '
        '"synonyms_native": "दमनकारी", "meaning": "holding back"}'
    ))
    sparse_retry = _response(200, _gemini_payload('{"translation": "ದಮನ"}'))

    with patch(
        "kannada_lookup.translator.requests.post", side_effect=[first, sparse_retry]
    ):
        result = GeminiProvider("k", "m", "Kannada").lookup("suppression")

    assert result.meaning == "holding back"     # English carried over
    assert result.example_native == ""          # wrong-script value dropped
    assert result.synonyms_native == ""


def test_retry_prompt_demands_the_complete_object():
    """Prompt wording is the first line of defence; the backfill is the
    backstop. Pin both."""
    bad = _response(200, _gemini_payload(_kannada_json("दमन")))
    good = _response(200, _gemini_payload(_kannada_json("ದಮನ")))
    with patch(
        "kannada_lookup.translator.requests.post", side_effect=[bad, good]
    ) as post:
        GeminiProvider("k", "m", "Kannada").lookup("suppression")
    retry_prompt = post.call_args_list[1].kwargs["json"]["contents"][0]["parts"][0]["text"]
    assert "COMPLETE JSON" in retry_prompt
    assert "example_native" in retry_prompt.split("wrong alphabet")[1]


def test_gemini_escalates_to_the_fallback_model_after_two_fast_failures(monkeypatch):
    """Speed-first, reliable-second: the fast model gets two attempts, and
    only then does the slower fallback run. Pins that the third request
    actually targets the fallback model, not just that a third call
    happened."""
    monkeypatch.setattr("kannada_lookup.config.GEMINI_FALLBACK_MODEL", "strong-model")
    replies = [
        _response(200, _gemini_payload(_kannada_json("दमन"))),      # fast, wrong
        _response(200, _gemini_payload(_kannada_json("কৃতজ্ঞতা"))),   # fast retry, wrong
        _response(200, _gemini_payload(_kannada_json("ದಮನ"))),      # fallback, right
    ]
    with patch("kannada_lookup.translator.requests.post", side_effect=replies) as post:
        result = GeminiProvider("k", "fast-model", "Kannada").lookup("suppression")

    assert result.translation == "ದಮನ"
    assert post.call_count == 3
    urls = [c.args[0] if c.args else c.kwargs.get("url", "") for c in post.call_args_list]
    assert "fast-model" in urls[0] and "fast-model" in urls[1]
    assert "strong-model" in urls[2]


def test_malformed_reply_is_retried_once():
    """A garbled reply is as transient as a 5xx — the model produced
    non-JSON that once. Observed "ephemeral" fail this way mid-run on an
    otherwise-healthy set of lookups."""
    replies = [
        _response(200, _gemini_payload("not json at all")),
        _response(200, _gemini_payload(_kannada_json("ದಮನ"))),
    ]
    with patch("kannada_lookup.translator.requests.post", side_effect=replies) as post:
        result = GeminiProvider("k", "m", "Kannada").lookup("suppression")
    assert result.translation == "ದಮನ"
    assert post.call_count == 2


def test_malformed_reply_retry_does_not_recurse():
    """Persistently garbled output must surface, not loop."""
    bad = _response(200, _gemini_payload("not json at all"))
    with patch("kannada_lookup.translator.requests.post", side_effect=[bad, bad]) as post:
        with pytest.raises(LookupFailed, match="model reply"):
            GeminiProvider("k", "m", "Kannada").lookup("suppression")
    assert post.call_count == 2


def test_transient_5xx_is_retried_once():
    """Google returning 503 means its side is briefly overloaded, not that
    the request is wrong — observed a 503 sink an otherwise-good fallback
    escalation. One immediate retry usually lands."""
    replies = [
        _response(503),
        _response(200, _gemini_payload(_kannada_json("ದಮನ"))),
    ]
    with patch("kannada_lookup.translator.requests.post", side_effect=replies) as post:
        result = GeminiProvider("k", "m", "Kannada").lookup("suppression")
    assert result.translation == "ದಮನ"
    assert post.call_count == 2


def test_transient_5xx_retry_does_not_recurse():
    """Two 5xx in a row must surface an error, not retry forever."""
    with patch(
        "kannada_lookup.translator.requests.post",
        side_effect=[_response(503), _response(503)],
    ) as post:
        with pytest.raises(LookupFailed, match="temporarily unavailable"):
            GeminiProvider("k", "m", "Kannada").lookup("suppression")
    assert post.call_count == 2


def test_fallback_call_gets_a_longer_timeout(monkeypatch):
    """The escalation model is slower by definition — holding it to the
    fast model's ceiling timed out the very call meant to rescue the
    lookup (observed against the live API on "gratitude")."""
    monkeypatch.setattr("kannada_lookup.config.GEMINI_FALLBACK_MODEL", "strong-model")
    monkeypatch.setattr("kannada_lookup.config.API_TIMEOUT_S", 10.0)
    monkeypatch.setattr("kannada_lookup.config.API_TIMEOUT_FALLBACK_S", 25.0)
    replies = [
        _response(200, _gemini_payload(_kannada_json("दमन"))),
        _response(200, _gemini_payload(_kannada_json("दमन"))),
        _response(200, _gemini_payload(_kannada_json("ದಮನ"))),
    ]
    with patch("kannada_lookup.translator.requests.post", side_effect=replies) as post:
        GeminiProvider("k", "fast-model", "Kannada").lookup("suppression")

    timeouts = [c.kwargs["timeout"] for c in post.call_args_list]
    assert timeouts[0] == 10.0 and timeouts[1] == 10.0  # fast path unchanged
    assert timeouts[2] == 25.0  # only the escalation gets the headroom


def test_gemini_does_not_escalate_when_the_fast_model_succeeds(monkeypatch):
    """The escalation must never cost latency on the common path."""
    monkeypatch.setattr("kannada_lookup.config.GEMINI_FALLBACK_MODEL", "strong-model")
    with patch(
        "kannada_lookup.translator.requests.post",
        return_value=_response(200, _gemini_payload(_kannada_json("ದಮನ"))),
    ) as post:
        GeminiProvider("k", "fast-model", "Kannada").lookup("suppression")
    assert post.call_count == 1


def test_gemini_skips_escalation_when_fallback_is_the_same_model(monkeypatch):
    """No point paying a third call to ask the same model a third time."""
    monkeypatch.setattr("kannada_lookup.config.GEMINI_FALLBACK_MODEL", "fast-model")
    bad = _response(200, _gemini_payload(_kannada_json("दमन")))
    with patch("kannada_lookup.translator.requests.post", side_effect=[bad, bad]) as post:
        with pytest.raises(LookupFailed, match="wrong script"):
            GeminiProvider("k", "fast-model", "Kannada").lookup("suppression")
    assert post.call_count == 2


def test_gemini_escalation_disabled_by_empty_fallback(monkeypatch):
    monkeypatch.setattr("kannada_lookup.config.GEMINI_FALLBACK_MODEL", "")
    bad = _response(200, _gemini_payload(_kannada_json("दमन")))
    with patch("kannada_lookup.translator.requests.post", side_effect=[bad, bad]) as post:
        with pytest.raises(LookupFailed, match="wrong script"):
            GeminiProvider("k", "fast-model", "Kannada").lookup("suppression")
    assert post.call_count == 2


def test_gemini_reports_both_problems_when_the_fallback_itself_fails(monkeypatch):
    """A quota error on the backstop must not masquerade as the real
    problem — the user's word still failed for a script reason, and the
    fallback model may be one they never configured."""
    monkeypatch.setattr("kannada_lookup.config.GEMINI_FALLBACK_MODEL", "strong-model")
    bad = _response(200, _gemini_payload(_kannada_json("दमन")))
    with patch(
        "kannada_lookup.translator.requests.post",
        side_effect=[bad, bad, _response(429)],
    ):
        with pytest.raises(LookupFailed) as excinfo:
            GeminiProvider("k", "fast-model", "Kannada").lookup("suppression")
    message = str(excinfo.value)
    assert "wrong script" in message
    assert "fallback model failed too" in message
    assert "Rate limit" in message  # the underlying cause is preserved


def test_gemini_404_names_the_model_actually_called(monkeypatch):
    """On escalation the failing model is the fallback, not GEMINI_MODEL —
    naming the wrong one sends the user to edit a setting that was fine."""
    monkeypatch.setattr("kannada_lookup.config.GEMINI_FALLBACK_MODEL", "strong-model")
    bad = _response(200, _gemini_payload(_kannada_json("दमन")))
    with patch(
        "kannada_lookup.translator.requests.post",
        side_effect=[bad, bad, _response(404)],
    ):
        with pytest.raises(LookupFailed) as excinfo:
            GeminiProvider("k", "fast-model", "Kannada").lookup("suppression")
    assert "strong-model" in str(excinfo.value)


def test_gemini_raises_when_every_attempt_is_wrong_script(monkeypatch):
    """Failing loudly keeps the bad answer out of the cache, which is keyed
    by word with no model in the key — a stored wrong-script row would be
    served forever. Three bad replies now, not two: the fast model gets
    two attempts and the fallback model one before this gives up."""
    monkeypatch.setattr("kannada_lookup.config.GEMINI_FALLBACK_MODEL", "strong-model")
    bad = _response(200, _gemini_payload(_kannada_json("दमन")))
    with patch(
        "kannada_lookup.translator.requests.post", side_effect=[bad, bad, bad]
    ) as post:
        with pytest.raises(LookupFailed, match="wrong script"):
            GeminiProvider("k", "fast-model", "Kannada").lookup("suppression")
    assert post.call_count == 3


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
    synonyms_native="ಬಲ, ಸಾಮರ್ಥ್ಯ",
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


def test_store_migrates_a_pre_v4_db_without_losing_rows(tmp_path):
    """Adding synonyms_native must not disturb existing rows: they are
    served from cache and never refetched, so the column simply stays
    empty for them rather than being backfilled with a guess."""
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.execute(
        """CREATE TABLE lookups_v2 (
            language TEXT NOT NULL, key TEXT NOT NULL,
            original TEXT NOT NULL, translation TEXT NOT NULL,
            part_of_speech TEXT NOT NULL DEFAULT '',
            meaning TEXT NOT NULL DEFAULT '',
            synonyms TEXT NOT NULL DEFAULT '',
            example_en TEXT NOT NULL DEFAULT '',
            example_native TEXT NOT NULL DEFAULT '',
            provider TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL DEFAULT 0,
            deleted INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (language, key))"""
    )
    con.execute(
        "INSERT INTO lookups_v2 (language, key, original, translation, "
        "synonyms, created_at) VALUES ('Kannada', 'sky', 'Sky', 'ಆಕಾಶ', "
        "'heavens', 1000.0)"
    )
    con.commit()
    con.close()

    store = LookupStore(db)  # runs the migration
    got = store.get("sky", "Kannada")
    assert got.translation == "ಆಕಾಶ"
    assert got.synonyms == "heavens"  # pre-existing data intact
    assert got.synonyms_native == ""  # new column, no invented value
    assert len(store.all_entries()) == 1


def test_store_migration_is_idempotent(tmp_path):
    """Migrations run on every launch, not once."""
    db = tmp_path / "t.db"
    LookupStore(db).put(_RESULT, "Kannada", provider="test")
    for _ in range(3):
        store = LookupStore(db)
    assert store.get("strength", "Kannada").synonyms_native == "ಬಲ, ಸಾಮರ್ಥ್ಯ"
    assert len(store.all_entries()) == 1


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


def test_register_never_reuses_a_filename(tmp_path, monkeypatch):
    """Uniqueness has to be monotonic, not just "not currently on disk".

    Two calls can land in the same millisecond, and because _clean_stale
    deletes the previous file, an exists()-based check would hand out an
    earlier name again — while the browser may still hold that very name
    cached, which is the failure this whole scheme exists to prevent.
    """
    monkeypatch.setattr(register, "OUT_DIR", tmp_path)
    store = LookupStore(tmp_path / "t.db")
    store.put(_RESULT, "Kannada", provider="test")

    names = [register.generate(store).name for _ in range(50)]
    assert len(set(names)) == len(names)


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


def test_generate_and_open_opens_a_raw_path_not_a_uri(tmp_path, monkeypatch):
    """Pins the actual fix. Reproduced live on a real machine:
    QDesktopServices.openUrl(QUrl.fromLocalFile(path)) reported success but
    opened nothing, and feeding the SAME file:// string to plain
    os.startfile() also opened nothing — so a file:// URI is unreliable on
    Windows independent of Qt. os.startfile() on the bare path worked
    every time. webbrowser.open() calls os.startfile() with whatever
    string it's given, so the only thing that matters here is that the
    string reaching it is a plain path — never something built with
    QUrl.fromLocalFile or pathlib's .as_uri()."""
    monkeypatch.setattr(register, "OUT_DIR", tmp_path)
    opened = {}
    monkeypatch.setattr(
        "webbrowser.open", lambda target: opened.setdefault("target", target)
    )

    store = LookupStore(tmp_path / "t.db")
    store.put(_RESULT, "Kannada", provider="test")
    returned_path = register.generate_and_open(store)

    assert opened["target"] == str(returned_path)
    assert not opened["target"].startswith("file:")  # the actual regression
    assert returned_path.exists()


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
