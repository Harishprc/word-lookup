package com.harish.wordlookup

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.harish.wordlookup.data.GeminiProvider
import com.harish.wordlookup.data.LookupRepository
import com.harish.wordlookup.data.LookupResult
import com.harish.wordlookup.data.cache.LookupDatabase
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** Cache-then-network round trip — same contract as CachedProvider in
 * translator.py: a miss calls the provider and persists; a hit never
 * touches the network again. */
@RunWith(RobolectricTestRunner::class)
class LookupRepositoryTest {
    private lateinit var db: LookupDatabase
    private lateinit var server: MockWebServer
    private var callCount = 0

    @Before
    fun setUp() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        db = Room.inMemoryDatabaseBuilder(context, LookupDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        server = MockWebServer()
        server.start()
        callCount = 0
    }

    @After
    fun tearDown() {
        db.close()
        server.shutdown()
    }

    private fun repository(clock: () -> Long = { 1_000L }): LookupRepository {
        val endpointTemplate = server.url("/").toString() + "%s:generateContent"
        return LookupRepository(
            dao = db.lookupDao(),
            providerFactory = { language ->
                callCount++
                GeminiProvider(
                    apiKey = "k", model = "m", language = language,
                    endpointTemplate = endpointTemplate,
                )
            },
            timeSource = clock,
        )
    }

    @Test
    fun `cache miss calls provider and persists the result`() = runTest {
        server.enqueue(MockResponse().setBody(
            """{"candidates":[{"content":{"parts":[{"text":"{\"translation\":\"ಕ\"}"}]}}]}"""
        ))
        val repo = repository()

        val result = repo.lookup("Sky", "Kannada")

        assertEquals("ಕ", result.translation)
        assertEquals(1, callCount)
    }

    @Test
    fun `cache hit never calls the provider again`() = runTest {
        server.enqueue(MockResponse().setBody(
            """{"candidates":[{"content":{"parts":[{"text":"{\"translation\":\"ಕ\"}"}]}}]}"""
        ))
        val repo = repository()
        repo.lookup("Sky", "Kannada")

        // Differently-cased/spaced input normalizes to the same key.
        val second = repo.lookup("  sky ", "Kannada")

        assertEquals("ಕ", second.translation)
        assertEquals(1, callCount) // provider constructed once, not twice
    }

    @Test
    fun `same word in a different language is a separate cache entry`() = runTest {
        server.enqueue(MockResponse().setBody(
            """{"candidates":[{"content":{"parts":[{"text":"{\"translation\":\"ಕ\"}"}]}}]}"""
        ))
        server.enqueue(MockResponse().setBody(
            """{"candidates":[{"content":{"parts":[{"text":"{\"translation\":\"आ\"}"}]}}]}"""
        ))
        val repo = repository()

        val kn = repo.lookup("Sky", "Kannada")
        val hi = repo.lookup("Sky", "Hindi")

        assertEquals("ಕ", kn.translation)
        assertEquals("आ", hi.translation)
        assertEquals(2, callCount)
    }

    @Test
    fun `deleted entry is a tombstone, not gone, and is not served from cache`() = runTest {
        server.enqueue(MockResponse().setBody(
            """{"candidates":[{"content":{"parts":[{"text":"{\"translation\":\"ಕ\"}"}]}}]}"""
        ))
        server.enqueue(MockResponse().setBody(
            """{"candidates":[{"content":{"parts":[{"text":"{\"translation\":\"ಕ2\"}"}]}}]}"""
        ))
        val repo = repository()
        repo.lookup("Sky", "Kannada")

        repo.delete("Kannada", "Sky")
        val afterDelete = repo.lookup("Sky", "Kannada")

        assertEquals("ಕ2", afterDelete.translation) // re-fetched, not served stale
        assertEquals(2, callCount)
    }

    @Test
    fun `register flow reflects only non-deleted rows`() = runTest {
        server.enqueue(MockResponse().setBody(
            """{"candidates":[{"content":{"parts":[{"text":"{\"translation\":\"ಕ\"}"}]}}]}"""
        ))
        val repo = repository()
        repo.lookup("Sky", "Kannada")
        repo.delete("Kannada", "Sky")

        val entries = repo.observeRegister().first()

        assertEquals(0, entries.size)
    }
}
