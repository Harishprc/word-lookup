package com.harish.wordlookup

import com.harish.wordlookup.data.sync.SyncEntry
import com.harish.wordlookup.data.sync.SyncMerger
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Pins the merge contract SyncWorker (Android) and `sync.py` (desktop)
 * both rely on: commutative, idempotent, tombstone-wins, newer-wins. Both
 * sides must independently converge to the same result regardless of
 * which device syncs first — these properties are what make that safe.
 */
class SyncMergerTest {
    private fun entry(
        key: String = "sky",
        translation: String = "a",
        updatedAt: Long = 1000L,
        deleted: Boolean = false,
        language: String = "Kannada",
    ) = SyncEntry(
        language = language, key = key, original = key, translation = translation,
        createdAt = updatedAt, updatedAt = updatedAt, deleted = deleted,
    )

    @Test
    fun `disjoint keys union without loss`() {
        val a = entry(key = "sky")
        val b = entry(key = "moon")
        val result = SyncMerger.merge(listOf(a), listOf(b))
        assertEquals(setOf(a, b), result.toSet())
    }

    @Test
    fun `same key, newer updatedAt wins`() {
        val older = entry(translation = "old", updatedAt = 1000L)
        val newer = entry(translation = "new", updatedAt = 2000L)

        assertEquals(listOf(newer), SyncMerger.merge(listOf(older), listOf(newer)))
        assertEquals(listOf(newer), SyncMerger.merge(listOf(newer), listOf(older)))
    }

    @Test
    fun `tombstone beats an older live row even with equal updatedAt`() {
        val live = entry(deleted = false, updatedAt = 1000L)
        val tombstone = entry(deleted = true, updatedAt = 1000L)

        assertEquals(listOf(tombstone), SyncMerger.merge(listOf(live), listOf(tombstone)))
    }

    @Test
    fun `a strictly newer live row beats an older tombstone`() {
        val tombstone = entry(deleted = true, updatedAt = 1000L)
        val revived = entry(deleted = false, updatedAt = 2000L, translation = "back")

        assertEquals(listOf(revived), SyncMerger.merge(listOf(tombstone), listOf(revived)))
    }

    @Test
    fun `merge is commutative`() {
        val a = listOf(entry(translation = "x", updatedAt = 5), entry(key = "moon", updatedAt = 1))
        val b = listOf(entry(translation = "y", updatedAt = 5), entry(key = "sun", updatedAt = 1))

        assertEquals(
            SyncMerger.merge(a, b).toSet(),
            SyncMerger.merge(b, a).toSet(),
        )
    }

    @Test
    fun `merge is idempotent`() {
        val a = listOf(entry(key = "sky"), entry(key = "moon"))
        assertEquals(a.toSet(), SyncMerger.merge(a, a).toSet())
    }

    @Test
    fun `different languages are different rows, never collapsed`() {
        val kn = entry(language = "Kannada")
        val hi = entry(language = "Hindi")
        val result = SyncMerger.merge(listOf(kn), listOf(hi))
        assertEquals(2, result.size)
    }

    @Test
    fun `three-way merge order does not matter (associativity)`() {
        val a = entry(translation = "a", updatedAt = 1)
        val b = entry(translation = "b", updatedAt = 2)
        val c = entry(translation = "c", updatedAt = 3)

        val leftFirst = SyncMerger.merge(SyncMerger.merge(listOf(a), listOf(b)), listOf(c))
        val rightFirst = SyncMerger.merge(listOf(a), SyncMerger.merge(listOf(b), listOf(c)))

        assertEquals(leftFirst.toSet(), rightFirst.toSet())
        assertTrue(leftFirst.single().translation == "c") // highest updatedAt wins overall
    }
}
