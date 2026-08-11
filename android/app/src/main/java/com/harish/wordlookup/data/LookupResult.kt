package com.harish.wordlookup.data

/**
 * One dictionary-card entry. Mirrors `kannada_lookup/translator.py`'s
 * `LookupResult` dataclass field-for-field so the phone and desktop cards
 * carry identical data. Only [original] and [translation] are guaranteed;
 * the English fields are empty on non-LLM providers — the UI hides empty
 * rows rather than showing blanks.
 */
data class LookupResult(
    val original: String,
    val translation: String,       // target-language translation
    val partOfSpeech: String = "", // noun/verb/adjective…; empty for phrases
    val meaning: String = "",      // concise English meaning
    val synonyms: String = "",     // 2-3 conversational-English synonyms, joined
    val exampleEn: String = "",    // one short example sentence in English
    val exampleNative: String = "", // one short example sentence in the target language
)

/** User-presentable failure (network, bad key, quota…) — same role as the
 * desktop's `LookupFailed` exception. */
class LookupFailedException(message: String) : Exception(message)
