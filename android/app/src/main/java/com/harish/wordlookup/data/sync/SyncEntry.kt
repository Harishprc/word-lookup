package com.harish.wordlookup.data.sync

import com.harish.wordlookup.data.cache.LookupEntity
import kotlinx.serialization.Serializable

/**
 * Wire format for the sync Gist — one JSON object per row, field-for-field
 * matching `LookupEntity` (Android) and the payload `kannada_lookup/sync.py`
 * writes (Python `snake_case` vs Kotlin `camelCase` reconciled at the
 * serialization boundary only, see [SyncPayload]).
 */
@Serializable
data class SyncEntry(
    val language: String,
    val key: String,
    val original: String,
    val translation: String,
    val partOfSpeech: String = "",
    val meaning: String = "",
    val synonyms: String = "",
    val exampleEn: String = "",
    val exampleNative: String = "",
    val provider: String = "",
    val createdAt: Long,
    val updatedAt: Long,
    val deleted: Boolean = false,
) {
    fun toEntity() = LookupEntity(
        language = language, key = key, original = original, translation = translation,
        partOfSpeech = partOfSpeech, meaning = meaning, synonyms = synonyms,
        exampleEn = exampleEn, exampleNative = exampleNative, provider = provider,
        createdAt = createdAt, updatedAt = updatedAt, deleted = deleted,
    )

    companion object {
        fun fromEntity(e: LookupEntity) = SyncEntry(
            language = e.language, key = e.key, original = e.original, translation = e.translation,
            partOfSpeech = e.partOfSpeech, meaning = e.meaning, synonyms = e.synonyms,
            exampleEn = e.exampleEn, exampleNative = e.exampleNative, provider = e.provider,
            createdAt = e.createdAt, updatedAt = e.updatedAt, deleted = e.deleted,
        )
    }
}

@Serializable
data class SyncPayload(val version: Int = 1, val entries: List<SyncEntry> = emptyList())
