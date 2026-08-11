package com.harish.wordlookup

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.harish.wordlookup.data.Settings
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** The `enabled` flag is the single source of truth read by the
 * accessibility service, the QS tile, and the main screen's toggle — this
 * pins the on/off/toggle contract they all rely on. */
@RunWith(RobolectricTestRunner::class)
class SettingsTest {
    private fun settings() = Settings(ApplicationProvider.getApplicationContext<Context>())

    @Test
    fun `defaults to enabled`() = runTest {
        assertTrue(settings().enabled.first())
    }

    @Test
    fun `toggleEnabled flips and returns the new value`() = runTest {
        val s = settings()
        val afterFirstToggle = s.toggleEnabled()
        assertEquals(false, afterFirstToggle)
        assertEquals(false, s.enabled.first())

        val afterSecondToggle = s.toggleEnabled()
        assertEquals(true, afterSecondToggle)
    }

    @Test
    fun `setTargetLanguage persists and is readable back`() = runTest {
        val s = settings()
        s.setTargetLanguage("Hindi")
        assertEquals("Hindi", s.targetLanguage.first())
    }
}
