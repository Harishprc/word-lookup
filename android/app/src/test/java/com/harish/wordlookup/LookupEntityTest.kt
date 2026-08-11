package com.harish.wordlookup

import com.harish.wordlookup.data.cache.LookupEntity
import org.junit.Assert.assertEquals
import org.junit.Test

/** Mirrors store.py's `_normalize` — the phone and desktop caches must key
 * identically or a sync merge (Phase 7) would treat "Hello" and "hello  "
 * as two different words instead of one. */
class LookupEntityTest {
    @Test
    fun `collapses internal whitespace and lowercases`() {
        assertEquals("hello world", LookupEntity.normalize("Hello   World"))
    }

    @Test
    fun `trims leading and trailing whitespace`() {
        assertEquals("hello", LookupEntity.normalize("  Hello \n"))
    }

    @Test
    fun `is idempotent`() {
        val once = LookupEntity.normalize("Ephemeral Joy")
        assertEquals(once, LookupEntity.normalize(once))
    }
}
