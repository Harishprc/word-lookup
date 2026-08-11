package com.harish.wordlookup

import com.harish.wordlookup.data.sync.GistSyncClient
import com.harish.wordlookup.data.sync.SyncEntry
import com.harish.wordlookup.data.sync.SyncPayload
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test

class GistSyncClientTest {
    private lateinit var server: MockWebServer

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    private fun client(pat: String = "token") =
        GistSyncClient(pat = pat, apiBase = server.url("/").toString().trimEnd('/'))

    @Test
    fun `blank gist id pulls nothing without a network call`() = runTest {
        val result = client().pull("")
        assertNull(result)
        assertEquals(0, server.requestCount)
    }

    @Test
    fun `blank token fails before any network call`() = runTest {
        try {
            client(pat = "").pull("abc123")
            fail("expected GistSyncException")
        } catch (e: GistSyncClient.GistSyncException) {
            assertTrue(e.message!!.contains("No GitHub token"))
        }
        assertEquals(0, server.requestCount)
    }

    @Test
    fun `pull parses the embedded lookups json out of the gist file`() = runTest {
        val payloadJson = """{"version":1,"entries":[{"language":"Kannada","key":"sky",
            |"original":"Sky","translation":"ಆಕಾಶ","partOfSpeech":"","meaning":"","synonyms":"",
            |"exampleEn":"","exampleNative":"","provider":"","createdAt":1000,"updatedAt":1000,
            |"deleted":false}]}""".trimMargin().replace("\"", "\\\"").replace("\n", "")
        val gistResponse = """{"id":"abc123","files":{"lookups.json":{"content":"$payloadJson"}}}"""
        server.enqueue(MockResponse().setBody(gistResponse))

        val result = client().pull("abc123")

        assertEquals(1, result?.entries?.size)
        assertEquals("ಆಕಾಶ", result?.entries?.first()?.translation)
    }

    @Test
    fun `404 on pull returns null, not an exception`() = runTest {
        server.enqueue(MockResponse().setResponseCode(404))
        assertNull(client().pull("missing"))
    }

    @Test
    fun `push with blank gist id POSTs and returns the new id`() = runTest {
        server.enqueue(MockResponse().setBody("""{"id":"new-id","files":{}}"""))

        val id = client().push("", SyncPayload(entries = listOf(sampleEntry())))

        assertEquals("new-id", id)
        val recorded = server.takeRequest()
        assertEquals("POST", recorded.method)
    }

    @Test
    fun `push with existing gist id PATCHes that id`() = runTest {
        server.enqueue(MockResponse().setBody("""{"id":"abc123","files":{}}"""))

        val id = client().push("abc123", SyncPayload(entries = listOf(sampleEntry())))

        assertEquals("abc123", id)
        val recorded = server.takeRequest()
        assertEquals("PATCH", recorded.method)
        assertEquals("Bearer token", recorded.getHeader("Authorization"))
    }

    @Test
    fun `409 on push maps to a retryable sync exception`() = runTest {
        server.enqueue(MockResponse().setResponseCode(409))
        try {
            client().push("abc123", SyncPayload())
            fail("expected GistSyncException")
        } catch (e: GistSyncClient.GistSyncException) {
            assertTrue(e.message!!.contains("concurrently"))
        }
    }

    private fun sampleEntry() = SyncEntry(
        language = "Kannada", key = "sky", original = "Sky", translation = "ಆಕಾಶ",
        createdAt = 1000, updatedAt = 1000,
    )
}
