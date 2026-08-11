package com.harish.wordlookup.data.cache

import androidx.room.Entity
import com.harish.wordlookup.data.LookupResult

/**
 * Mirrors `kannada_lookup/store.py`'s `lookups_v2` schema — same columns,
 * same composite primary key `(language, key)`, so the sync payload
 * (Phase 7) maps 1:1 onto both sides with no field renaming.
 *
 * [updatedAt] and [deleted] have no desktop-schema v2 counterpart; they
 * exist from day one here so Phase 7 (Gist sync) needs no later migration
 * on the Android side. `updatedAt` drives last-write-wins merge; `deleted`
 * is a tombstone so a phone-side delete doesn't resurrect on next sync —
 * see `store.py`'s `_migrate_v1` for the desktop-side migration pattern.
 */
@Entity(tableName = "lookups", primaryKeys = ["language", "key"])
data class LookupEntity(
    val language: String,
    val key: String,           // normalized (whitespace-collapsed, lowercased) text
    val original: String,
    val translation: String,
    val partOfSpeech: String = "",
    val meaning: String = "",
    val synonyms: String = "",
    val exampleEn: String = "",
    val exampleNative: String = "",
    val provider: String = "",
    val createdAt: Long,        // epoch millis
    val updatedAt: Long,        // epoch millis — sync merge key
    val deleted: Boolean = false,
) {
    fun toResult() = LookupResult(
        original = original,
        translation = translation,
        partOfSpeech = partOfSpeech,
        meaning = meaning,
        synonyms = synonyms,
        exampleEn = exampleEn,
        exampleNative = exampleNative,
    )

    companion object {
        /** Same whitespace-collapse + lowercase rule as store.py's
         * `_normalize` — the two caches must key identically for sync to
         * ever line up a phone row with a desktop row. */
        fun normalize(text: String): String =
            text.trim().split(Regex("\\s+")).joinToString(" ").lowercase()
    }
}
