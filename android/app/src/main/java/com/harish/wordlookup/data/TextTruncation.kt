package com.harish.wordlookup.data

/**
 * Same rule as the desktop's `config.MAX_CHARS` (500): cap the text sent
 * to the API, cut at the last space so a word isn't sliced mid-way. Split
 * out as a pure function (rather than inline in ProcessTextActivity) so
 * it's testable on the plain JVM, no Android framework needed.
 */
object TextTruncation {
    const val MAX_CHARS = 500

    fun truncate(text: String, max: Int = MAX_CHARS): String {
        val trimmed = text.trim()
        if (trimmed.length <= max) return trimmed
        val cut = trimmed.substring(0, max)
        val lastSpace = cut.lastIndexOf(' ')
        return if (lastSpace > 0) cut.substring(0, lastSpace) else cut
    }
}
