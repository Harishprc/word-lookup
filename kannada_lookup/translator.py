"""Provider-agnostic translation backend.

Default provider: GeminiProvider — Gemini API with a Google AI Studio key.
An LLM provider returns meaning AND an example sentence, matching the
original Apple-Dictionary-style spec. Swap providers via PROVIDER in .env,
zero code changes at call sites (GoogleTranslateProvider kept as fallback;
a paid Claude/GPT provider can slot in later the same way).

COST NOTE (Gemini via AI Studio key):
  - Free tier, permanent, no credit card: roughly 1,500 requests/day on
    flash-lite class models (10-30 req/min). Ample for personal lookups.
  - Caveat: Google may use free-tier prompts to improve its models —
    fine for single-word lookups, don't send anything sensitive.

COST NOTE (Google Cloud Translation, legacy fallback):
  - First 500,000 characters/month free, then $20 per 1M characters.
    Requires a GCP project WITH billing enabled even for free usage.
"""

import html
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass

import requests

from . import config


@dataclass(frozen=True)
class LookupResult:
    """One dictionary-card entry. Only `original` and `translation` are
    guaranteed; the English fields come from LLM providers and stay empty
    on plain-translation providers — the popup hides empty rows."""

    original: str
    translation: str          # target-language translation
    part_of_speech: str = ""  # noun/verb/adjective…; empty for phrases
    meaning: str = ""         # concise English meaning
    synonyms: str = ""        # 2-3 conversational-English synonyms, joined
    example_en: str = ""      # one short example sentence in English
    example_native: str = ""  # one short example sentence in the target language


class LookupFailed(Exception):
    """User-presentable failure (network, bad key, quota…)."""


class TranslationProvider(ABC):
    @abstractmethod
    def lookup(self, text: str) -> LookupResult: ...


class GeminiProvider(TranslationProvider):
    """Gemini API (AI Studio key) — full dictionary card in one call."""

    ENDPOINT = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "{model}:generateContent"
    )

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
        '"example_native": "<one short, simple example sentence written in '
        "{language} that uses that word>\"}}\n"
        "For multi-word phrases, synonyms may be an empty list.\n\n"
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

    def lookup(self, text: str) -> LookupResult:
        try:
            resp = requests.post(
                self.ENDPOINT.format(model=self._model),
                headers={"x-goog-api-key": self._key},
                json={
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "text": self._PROMPT.format(
                                        text=text, language=self._language
                                    )
                                }
                            ],
                        }
                    ],
                    # Forces raw JSON output — no prose, no markdown fences
                    # (fences still stripped below, belt and suspenders).
                    "generationConfig": {"responseMimeType": "application/json"},
                },
                timeout=config.API_TIMEOUT_S,
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
            raise LookupFailed(
                "Free-tier quota hit (~1,500/day). Wait a minute or try tomorrow."
            )
        if resp.status_code == 404:
            raise LookupFailed(
                f"Model '{self._model}' not found — set GEMINI_MODEL in .env "
                "(e.g. gemini-2.0-flash)."
            )
        if not resp.ok:
            raise LookupFailed(f"Gemini API error {resp.status_code}.")

        try:
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, ValueError):
            raise LookupFailed("Unexpected API response format.")

        data = self._parse_json(raw)
        translation = str(data.get("translation", "")).strip()
        if not translation:
            raise LookupFailed("No translation returned — try again.")

        synonyms = data.get("synonyms", "")
        if isinstance(synonyms, list):  # model may return list or string
            synonyms = ", ".join(str(s).strip() for s in synonyms if str(s).strip())

        return LookupResult(
            original=text,
            translation=translation,
            part_of_speech=str(data.get("part_of_speech", "")).strip().lower(),
            meaning=str(data.get("meaning", "")).strip(),
            synonyms=str(synonyms).strip(),
            example_en=str(data.get("example_en", "")).strip(),
            example_native=str(data.get("example_native", "")).strip(),
        )

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
            raise LookupFailed("Could not read model reply — try again.")
        if not isinstance(parsed, dict):
            raise LookupFailed("Could not read model reply — try again.")
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
            raise LookupFailed("Unexpected API response format.")

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
    """Factory keyed on PROVIDER from .env — the provider swap point."""
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
