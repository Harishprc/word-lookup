"""Provider-agnostic translation backend.

Default provider: GeminiProvider - Gemini API with a Google AI Studio key.
An LLM provider returns meaning AND an example sentence, matching the
original Apple-Dictionary-style spec. Swap providers via PROVIDER in .env,
zero code changes at call sites (GoogleTranslateProvider kept as fallback;
a paid Claude/GPT provider can slot in later the same way).

COST NOTE (Gemini via AI Studio key):
  - Free tier, permanent, no credit card. The allowance depends on the
    model: flash-lite class (the default) is the most generous
    (~1,500/day) and, measured against the real API, 2-4x faster per
    lookup than plain flash class - the latter isn't just cheaper on
    quota, it's the difference between a 3s popup and one that
    occasionally times out. Ample either way for reading, since repeats
    are served from cache; a bulk pass over the whole cache is what
    actually trips the per-minute limit (see
    scripts/backfill_native_synonyms.py).
  - Caveat: Google may use free-tier prompts to improve its models -
    fine for single-word lookups, don't send anything sensitive.

COST NOTE (Google Cloud Translation, legacy fallback):
  - First 500,000 characters/month free, then $20 per 1M characters.
    Requires a GCP project WITH billing enabled even for free usage.
"""

import html
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace

import requests

from . import config, languages


@dataclass(frozen=True)
class LookupResult:
    """One dictionary-card entry. Only `original` and `translation` are
    guaranteed; the English fields come from LLM providers and stay empty
    on plain-translation providers - the popup hides empty rows."""

    original: str
    translation: str          # target-language translation
    part_of_speech: str = ""  # noun/verb/adjective…; empty for phrases
    meaning: str = ""         # concise English meaning
    synonyms: str = ""        # 2-3 conversational-English synonyms, joined
    example_en: str = ""      # one short example sentence in English
    example_native: str = ""  # one short example sentence in the target language
    # 2-3 synonyms of the *translation*, in the target language. Empty on
    # rows cached before this field existed (they are served from cache and
    # never refetched) and on plain-translation providers.
    synonyms_native: str = ""


class LookupFailed(Exception):
    """User-presentable failure (network, bad key, quota…)."""


class MalformedReply(LookupFailed):
    """The model returned something unparseable this time.

    A LookupFailed subclass so every existing `except LookupFailed`
    handler and user-facing message path is unchanged, but distinguishable
    internally: unlike a bad key or exhausted quota, this is transient -
    the same request usually succeeds on an immediate second attempt - so
    _request retries once on it, exactly like a 5xx.
    """


class TranslationProvider(ABC):
    @abstractmethod
    def lookup(self, text: str) -> LookupResult: ...


class GeminiProvider(TranslationProvider):
    """Gemini API (AI Studio key) - full dictionary card in one call."""

    ENDPOINT = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "{model}:generateContent"
    )

    # The translation rules exist because weaker models invent
    # plausible-looking words in low-resource scripts: asking for
    # "restricted" in Kannada produced "ಮಿಚ್ಛಿತ / ನಿಯನ್ಶ್ರಿತ" - neither is a
    # real word, and the second is a malformed consonant cluster that
    # renders with a dotted circle (the Unicode orphaned-combining-mark
    # marker). Naming the failure modes explicitly is what suppresses them.
    _PROMPT = (
        "You are an English-{language} dictionary. For the English word or "
        "phrase below, reply with ONLY this JSON:\n"
        '{{"part_of_speech": "<noun/verb/adjective/adverb/…, or empty for '
        'multi-word phrases>", '
        '"meaning": "<short, plain English meaning>", '
        '"synonyms": ["<2-3 synonyms common in conversational English>"], '
        '"example_en": "<one short, simple example sentence in English '
        'that uses the word>", '
        '"translation": "<the {language} translation>", '
        '"synonyms_native": ["<2-3 {language} synonyms of that '
        'translation, written in {language} script>"], '
        '"example_native": "<one short, simple example sentence written in '
        "{language} that uses that word>\"}}\n"
        "For multi-word phrases, synonyms may be an empty list.\n\n"
        "Rules for the {language} text:\n"
        "- synonyms_native must be synonyms of the {language} translation, "
        "not translations of the English synonyms, and must not repeat the "
        "translation itself. Use an empty list if there is no natural "
        "{language} synonym rather than padding it with loose matches.\n"
        "- Give exactly ONE translation: the single most commonly used "
        "word. Never offer alternatives, and never use a slash.\n"
        "- It must be a real, standard {language} word that a native "
        "speaker would recognise and a dictionary would list. If no true "
        "equivalent exists, use the ordinary {language} phrase for the "
        "idea rather than inventing a word.\n"
        "- Write it in correct, well-formed {language} script. Never "
        "spell the English word out phonetically in that script.\n"
        "- Use only valid letter combinations for {language}. Do not "
        "produce malformed clusters.\n\n"
        "English: {text}"
    )

    def __init__(self, api_key: str, model: str, language: str):
        if not api_key:
            raise LookupFailed(
                "No API key. Get a free one at aistudio.google.com and set "
                "GEMINI_API_KEY in .env."
            )
        self._key = api_key
        self._model = model
        self._language = language

    # Appended to the prompt on the one retry after a wrong-script reply.
    # Naming the mistake concretely works better than repeating the
    # original instruction, which the model has already ignored once.
    _RETRY_SUFFIX = (
        "\n\nYour previous answer was written in the wrong alphabet. The "
        "translation MUST be written in the {language} script itself, not "
        "in the script of any other language, and not in Latin letters. "
        "Reply again with the COMPLETE JSON object — every field above, "
        "including example_native and synonyms_native, filled in exactly "
        "as specified. Do not return only the translation."
    )

    def lookup(self, text: str) -> LookupResult:
        """Fast model first, escalate to a stronger one only if it fails.

        Speed is the priority: the default model answers in ~1.5-3s and
        gets the script right on the large majority of words, so the
        common path is one request and nothing here fires. Reliability is
        the backstop: on a wrong-script reply this retries the fast model
        once (naming the mistake), and only if THAT also fails does it
        escalate to GEMINI_FALLBACK_MODEL - measured 2-4x slower, but paid
        for the handful of words that actually need it rather than on
        every lookup.

        The escalation is what stops a hard word being a dead end. Before
        it, "gratitude" and "suppression" in Kannada exhausted both fast
        attempts and surfaced an error; the strong model gets them right,
        and CachedProvider stores the result, so each hard word costs the
        slow path at most once ever.
        """
        result = self._request(text)
        if languages.uses_expected_script(result.translation, self._language):
            return result

        # Wrong script is unambiguous and cheap to detect, and a wrong-script
        # card is useless - the reader cannot even read it. Retry once with
        # the mistake spelled out rather than caching the bad answer.
        retry_prompt = self._RETRY_SUFFIX.format(language=self._language)
        retried = self._request(text, extra=retry_prompt)
        if languages.uses_expected_script(retried.translation, self._language):
            return self._backfill_english(retried, result)

        fallback = config.GEMINI_FALLBACK_MODEL
        if fallback and fallback != self._model:
            try:
                escalated = self._request(text, extra=retry_prompt, model=fallback)
            except LookupFailed as e:
                # The fallback is a best-effort backstop, so its own
                # failure (quota, a retired model name) must not replace
                # the real problem with a confusing one about a model the
                # user may never have configured. Report both.
                raise LookupFailed(
                    f"Model answered in the wrong script for {self._language} "
                    f"twice, and the fallback model failed too: {e}"
                )
            if languages.uses_expected_script(escalated.translation, self._language):
                return self._backfill_english(escalated, result)

        # Still wrong: fail loudly instead of returning something unreadable.
        # Raising also keeps it out of the cache, which is keyed by word only
        # - a bad entry stored here would be served forever.
        raise LookupFailed(
            f"Model answered in the wrong script for {self._language}. "
            "Try again, or switch GEMINI_MODEL in .env."
        )

    # Fields that describe the ENGLISH side of the card. Safe to carry
    # over from a rejected attempt; the target-language fields are not.
    _ENGLISH_FIELDS = ("part_of_speech", "meaning", "synonyms", "example_en")

    @classmethod
    def _backfill_english(cls, primary: LookupResult, earlier: LookupResult):
        """Fill blanks in `primary` from an earlier, script-rejected reply.

        Asking the model to "reply again, in <language> script" makes it
        treat the translation as the whole task: a retry for "configuration"
        came back with example_native empty, and that empty value was then
        cached, which is why some cards showed no native example sentence.

        The prompt now asks for the complete object, but prompt wording is
        not a guarantee, so this backstops it in code. ONLY the English
        fields are copied: the earlier reply was rejected for being in the
        wrong script, so its translation, example_native and
        synonyms_native are exactly the values that must not be reused -
        while its meaning and English example were never in question.
        """
        patch = {
            f: getattr(earlier, f)
            for f in cls._ENGLISH_FIELDS
            if not str(getattr(primary, f)).strip()
            and str(getattr(earlier, f)).strip()
        }
        return replace(primary, **patch) if patch else primary

    def _request(
        self, text: str, extra: str = "", model: str = "", _retrying: bool = False
    ) -> LookupResult:
        """`model` overrides the configured one for a single call - used
        only by lookup()'s fallback escalation, so the slower model is
        paid for exactly the words that need it.

        `_retrying` is internal: set on the one automatic retry after a
        transient 5xx, so that path can't recurse."""
        prompt = self._PROMPT.format(text=text, language=self._language) + extra
        try:
            resp = requests.post(
                self.ENDPOINT.format(model=model or self._model),
                headers={"x-goog-api-key": self._key},
                json={
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": prompt}],
                        }
                    ],
                    # Forces raw JSON output - no prose, no markdown fences
                    # (fences still stripped below, belt and suspenders).
                    "generationConfig": {"responseMimeType": "application/json"},
                },
                # A fallback call is the slow model by definition; holding
                # it to the fast model's ceiling would time out the very
                # attempt meant to rescue the lookup.
                timeout=(
                    config.API_TIMEOUT_FALLBACK_S if model else config.API_TIMEOUT_S
                ),
            )
        except requests.exceptions.Timeout:
            raise LookupFailed("Lookup timed out — check your connection.")
        except requests.exceptions.ConnectionError:
            raise LookupFailed("No internet connection.")

        if resp.status_code in (400, 401, 403):
            raise LookupFailed(
                f"API key rejected ({resp.status_code}). Check GEMINI_API_KEY in .env."
            )
        if resp.status_code == 429:
            # Deliberately vague on numbers: the limit depends on the model
            # (flash-lite allows far more per day than flash) and Google
            # changes them, so quoting a figure here goes stale and misleads.
            # 429 is also per-minute as often as per-day, hence "a minute".
            raise LookupFailed(
                "Rate limit or daily quota hit. Wait a minute and try again."
            )
        if resp.status_code == 404:
            # Names the model actually called, not self._model - on a
            # fallback escalation those differ, and reporting the wrong
            # one sends the user to edit a setting that was never at fault.
            raise LookupFailed(
                f"Model '{model or self._model}' not found — set GEMINI_MODEL "
                "in .env (e.g. gemini-2.0-flash)."
            )
        if resp.status_code in (500, 502, 503, 504):
            # Google's side is transiently overloaded - nothing about the
            # request is wrong, so one immediate retry usually lands.
            # Observed a 503 sink an otherwise-good fallback escalation.
            # Guarded by `not _retrying` so this can never recurse further
            # than a single extra attempt.
            if not _retrying:
                return self._request(text, extra, model, _retrying=True)
            raise LookupFailed(
                f"Gemini is temporarily unavailable ({resp.status_code}). "
                "Try again in a moment."
            )
        if not resp.ok:
            raise LookupFailed(f"Gemini API error {resp.status_code}.")

        # A garbled reply is as transient as a 5xx - the model simply
        # produced non-JSON that once, and asking again usually works.
        # Observed "ephemeral" fail this way on an otherwise-healthy run.
        # Same single-retry guard, so a persistently broken reply still
        # surfaces rather than looping.
        try:
            try:
                raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError, ValueError):
                raise MalformedReply("Unexpected API response format.")
            data = self._parse_json(raw)
        except MalformedReply:
            if not _retrying:
                return self._request(text, extra, model, _retrying=True)
            raise

        translation = str(data.get("translation", "")).strip()
        if not translation:
            raise LookupFailed("No translation returned — try again.")

        synonyms = self._join_synonyms(data.get("synonyms", ""))
        synonyms_native = self._join_synonyms(data.get("synonyms_native", ""))

        # Models sometimes answer the synonym field with the translation
        # itself, which reads as a duplicate on the card. Dropping it here
        # is cheaper than another round trip and can only ever remove a
        # word the user is already looking at.
        if synonyms_native:
            kept = [
                s for s in synonyms_native.split(", ") if s.strip() != translation
            ]
            synonyms_native = ", ".join(kept)

        return LookupResult(
            original=text,
            translation=translation,
            part_of_speech=str(data.get("part_of_speech", "")).strip().lower(),
            meaning=str(data.get("meaning", "")).strip(),
            synonyms=synonyms,
            example_en=str(data.get("example_en", "")).strip(),
            example_native=str(data.get("example_native", "")).strip(),
            synonyms_native=synonyms_native,
        )

    @staticmethod
    def _join_synonyms(value) -> str:
        """Models return this field as either a JSON list or an
        already-joined string, depending on the model and the day."""
        if isinstance(value, list):
            return ", ".join(str(s).strip() for s in value if str(s).strip())
        return str(value).strip()

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """Parse model output; tolerate ```json fences some models emit."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]  # drop ```json line
            cleaned = cleaned.rsplit("```", 1)[0]
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            raise MalformedReply("Could not read model reply — try again.")
        if not isinstance(parsed, dict):
            raise MalformedReply("Could not read model reply — try again.")
        return parsed


class GoogleTranslateProvider(TranslationProvider):
    ENDPOINT = "https://translation.googleapis.com/language/translate/v2"

    def __init__(self, api_key: str):
        if not api_key:
            raise LookupFailed(
                "No API key. Copy .env.example to .env and set GOOGLE_API_KEY."
            )
        self._key = api_key

    def lookup(self, text: str) -> LookupResult:
        try:
            resp = requests.post(
                self.ENDPOINT,
                headers={"x-goog-api-key": self._key},
                data={
                    "q": text,
                    "source": config.SOURCE_LANG,
                    "target": config.TARGET_LANG,
                    "format": "text",
                },
                timeout=config.API_TIMEOUT_S,
            )
        except requests.exceptions.Timeout:
            raise LookupFailed("Translation timed out — check your connection.")
        except requests.exceptions.ConnectionError:
            raise LookupFailed("No internet connection.")

        if resp.status_code == 403:
            raise LookupFailed("API key rejected (403). Check GOOGLE_API_KEY in .env.")
        if resp.status_code == 429:
            raise LookupFailed("Quota exceeded (429). Check GCP billing/quotas.")
        if not resp.ok:
            raise LookupFailed(f"Translation API error {resp.status_code}.")

        try:
            translated = resp.json()["data"]["translations"][0]["translatedText"]
        except (KeyError, IndexError, ValueError):
            raise MalformedReply("Unexpected API response format.")

        # v2 API HTML-escapes some entities even with format=text.
        return LookupResult(original=text, translation=html.unescape(translated))


class CachedProvider(TranslationProvider):
    """Wraps any provider with the persistent SQLite store (see store.py).

    Hit  -> instant, free, works offline.
    Miss -> inner provider (API) -> saved for next time.
    Replaces the old per-process lru_cache: same speed win, but survives
    restarts and doubles as the offline mode.
    """

    def __init__(self, inner: TranslationProvider, store):
        self._inner = inner
        self._store = store

    def lookup(self, text: str) -> LookupResult:
        language = config.TARGET_LANGUAGE  # cache is per-language
        cached = self._store.get(text, language)
        if cached is not None:
            return cached
        result = self._inner.lookup(text)
        self._store.put(result, language, provider=type(self._inner).__name__)
        return result


def make_provider() -> TranslationProvider:
    """Factory keyed on PROVIDER from .env - the provider swap point."""
    if config.PROVIDER == "gemini":
        inner = GeminiProvider(
            config.GEMINI_API_KEY, config.GEMINI_MODEL, config.TARGET_LANGUAGE
        )
    elif config.PROVIDER == "google":
        inner = GoogleTranslateProvider(config.GOOGLE_API_KEY)
    else:
        raise LookupFailed(f"Unknown PROVIDER '{config.PROVIDER}' in .env.")

    # Imported here, not at module top: store.py imports LookupResult from
    # this module, so a top-level import would be circular.
    from .store import LookupStore

    return CachedProvider(inner, LookupStore())
