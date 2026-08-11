package com.harish.wordlookup.data

import com.harish.wordlookup.data.cache.LookupDao
import com.harish.wordlookup.data.cache.LookupEntity
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

/**
 * Cache-then-network, matching the desktop's `CachedProvider`
 * (translator.py:217-237): hit is instant/offline/free, miss calls Gemini
 * and saves the result for next time. `TimeSource` is injected so tests can
 * control `updatedAt`/`createdAt` deterministically instead of touching
 * wall-clock time.
 */
class LookupRepository(
    private val dao: LookupDao,
    // Takes the resolved language rather than reading Settings itself, so
    // the cache-key language and the prompt language can never drift apart
    // (they were two independent reads before this), and so this never
    // blocks its caller's thread on a DataStore read — callers resolve the
    // language once via a suspend `settings.targetLanguage.first()` before
    // calling [lookup].
    private val providerFactory: (language: String) -> GeminiProvider,
    private val timeSource: () -> Long = System::currentTimeMillis,
) {
    suspend fun lookup(text: String, language: String): LookupResult {
        val key = LookupEntity.normalize(text)
        dao.get(language, key)?.let { return it.toResult() }

        val result = providerFactory(language).lookup(text)
        val now = timeSource()
        dao.upsert(
            LookupEntity(
                language = language,
                key = key,
                original = result.original,
                translation = result.translation,
                partOfSpeech = result.partOfSpeech,
                meaning = result.meaning,
                synonyms = result.synonyms,
                exampleEn = result.exampleEn,
                exampleNative = result.exampleNative,
                provider = "GeminiProvider",
                createdAt = now,
                updatedAt = now,
            )
        )
        return result
    }

    fun observeRegister(): Flow<List<RegisterEntry>> =
        dao.observeAll().map { rows -> rows.map { RegisterEntry(it.toResult(), it.language, it.createdAt) } }

    suspend fun delete(language: String, original: String) {
        dao.softDelete(language, LookupEntity.normalize(original), timeSource())
    }
}

/** One row for the register screen — same shape as `register.py`'s
 * per-entry dict (`result`, `language`, `created_at`). */
data class RegisterEntry(val result: LookupResult, val language: String, val createdAtMillis: Long)
