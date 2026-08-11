package com.harish.wordlookup

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * Pins the two conventions that arrive on TYPE_VIEW_TEXT_SELECTION_CHANGED.
 * Reading only the first is why selecting text in Brave/Chrome never fired
 * the instant card and always fell through to the PROCESS_TEXT menu.
 *
 * The logic under test is duplicated here rather than driving a real
 * AccessibilityEvent: that class is final with no public constructor, so a
 * plain JVM test cannot build one, and Robolectric's shadow does not let
 * fromIndex/toIndex be set independently of the text. Keeping the branch
 * table in one readable place is worth more than the indirection — if
 * SelectionAccessibilityService.extractSelection changes shape, this file
 * must change with it.
 */
class SelectionExtractionTest {

    /** Mirrors SelectionAccessibilityService.extractSelection. */
    private fun extract(
        eventText: String?,
        nodeText: String?,
        start: Int,
        end: Int,
    ): String? {
        val event = eventText?.takeIf { it.isNotBlank() }

        if (start < 0 || end < 0) {
            return event?.takeIf { it != nodeText }
        }
        if (start == end) return null

        val full = event ?: nodeText ?: return null
        val lo = minOf(start, end).coerceIn(0, full.length)
        val hi = maxOf(start, end).coerceIn(0, full.length)
        if (lo == hi) return null
        return full.substring(lo, hi)
    }

    // --- WebView convention (Chrome, Brave, in-app browsers) -------------

    @Test
    fun `webview selection with unset indices returns the event text`() {
        // The regression: this used to be rejected outright on start < 0.
        assertEquals("purification", extract("purification", null, -1, -1))
    }

    @Test
    fun `webview event echoing the whole node is not a selection`() {
        val whole = "The whole human life is meant for purification."
        assertNull(extract(whole, whole, -1, -1))
    }

    @Test
    fun `unset indices with no text yields nothing`() {
        assertNull(extract(null, "some node text", -1, -1))
        assertNull(extract("   ", null, -1, -1))
    }

    // --- Standard widget convention (TextView, EditText) -----------------

    @Test
    fun `standard widget slices the full text by the selection range`() {
        // event.text is the node's ENTIRE text here — returning it whole
        // would ship a paragraph to the API instead of the one word.
        assertEquals("human", extract("The whole human life", null, 10, 15))
    }

    @Test
    fun `falls back to node text when the event carries none`() {
        assertEquals("human", extract(null, "The whole human life", 10, 15))
    }

    @Test
    fun `reversed indices still slice correctly`() {
        assertEquals("human", extract("The whole human life", null, 15, 10))
    }

    @Test
    fun `caret move selects nothing`() {
        assertNull(extract("The whole human life", null, 7, 7))
    }

    @Test
    fun `indices past the end are clamped rather than crashing`() {
        assertEquals("life", extract("The whole human life", null, 16, 9999))
    }
}
