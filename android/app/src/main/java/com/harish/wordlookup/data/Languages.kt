package com.harish.wordlookup.data

/**
 * Curated target-language list — verbatim port of `kannada_lookup/languages.py`.
 * [name] is interpolated straight into the Gemini prompt, so keep it in sync
 * with the desktop list if you add a language there; [code] is unused here
 * (only the desktop's legacy Google-Translate provider needs an ISO code),
 * kept for parity. [glyph] is a single native character shown in the
 * language picker.
 */
data class Language(val name: String, val code: String, val glyph: String)

object Languages {
    val ALL: List<Language> = listOf(
        // Indian languages
        Language("Kannada", "kn", "ಕ"),
        Language("Hindi", "hi", "अ"),
        Language("Tamil", "ta", "த"),
        Language("Telugu", "te", "త"),
        Language("Malayalam", "ml", "മ"),
        Language("Marathi", "mr", "म"),
        Language("Bengali", "bn", "ব"),
        Language("Gujarati", "gu", "ગ"),
        Language("Punjabi", "pa", "ਪ"),
        Language("Odia", "or", "ଓ"),
        Language("Urdu", "ur", "ا"),
        // World languages
        Language("Spanish", "es", "Ñ"),
        Language("French", "fr", "Ç"),
        Language("German", "de", "ß"),
        Language("Japanese", "ja", "あ"),
        Language("Korean", "ko", "한"),
        Language("Chinese (Simplified)", "zh", "中"),
        Language("Arabic", "ar", "ع"),
        Language("Russian", "ru", "Я"),
        Language("Portuguese", "pt", "Ã"),
        Language("Italian", "it", "È"),
        Language("Turkish", "tr", "Ş"),
        Language("Vietnamese", "vi", "ơ"),
        Language("Thai", "th", "ท"),
        Language("Indonesian", "id", "ᬅ"),
    )

    private val byName = ALL.associateBy { it.name }

    val DEFAULT = ALL.first { it.name == "Kannada" }

    /** Tolerant of unknown names (e.g. a hand-edited settings blob) —
     * falls back to a generic glyph, same as languages.py's `get()`. */
    fun get(name: String): Language =
        byName[name] ?: Language(name, "", name.firstOrNull()?.uppercase() ?: "?")
}
