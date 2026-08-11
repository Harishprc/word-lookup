package com.harish.wordlookup

import com.harish.wordlookup.data.TextTruncation
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TextTruncationTest {
    @Test
    fun `short text passes through unchanged`() {
        assertEquals("hello world", TextTruncation.truncate("hello world"))
    }

    @Test
    fun `long text is cut at a word boundary, not mid-word`() {
        val long = "word ".repeat(200).trim() // 999 chars, all whole words
        val result = TextTruncation.truncate(long, max = 500)

        assertTrue(result.length <= 500)
        assertTrue("truncated text must not end mid-word", long.startsWith(result))
        assertEquals(' ', long[result.length]) // char right after the cut was a space boundary
    }

    @Test
    fun `a single word longer than max is hard-cut, not left uncapped`() {
        val long = "x".repeat(600)
        val result = TextTruncation.truncate(long, max = 500)
        assertEquals(500, result.length)
    }
}
