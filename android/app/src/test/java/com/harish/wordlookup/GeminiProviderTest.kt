package com.harish.wordlookup

import com.harish.wordlookup.data.GeminiProvider
import com.harish.wordlookup.data.LookupFailedException
import kotlinx.coroutines.test.runTest
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test

/**
 * Ports the behaviors verified in tests/test_translator.py for the desktop
 * GeminiProvider: fence-stripped JSON parses, synonyms as list or string,
 * and every documented status-code error message. Talks to a MockWebServer
 * instead of the real Gemini host via GeminiProvider's test-only
 * `endpointTemplate` override.
 */
class GeminiProviderTest {
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

    private fun provider(): GeminiProvider {
        val endpointTemplate = server.url("/").toString() + "%s:generateContent"
        return GeminiProvider(
            apiKey = "test-key",
            model = "gemini-flash-lite-latest",
            language = "Kannada",
            client = OkHttpClient.Builder().build(),
            endpointTemplate = endpointTemplate,
        )
    }

    private fun candidateBody(text: String): String {
        val escaped = text.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")
        return """{"candidates":[{"content":{"parts":[{"text":"$escaped"}]}}]}"""
    }

    @Test
    fun `blank api key fails before any network call`() = runTest {
        val provider = GeminiProvider(apiKey = "", model = "m", language = "Kannada")
        try {
            provider.lookup("hello")
            fail("expected LookupFailedException")
        } catch (e: LookupFailedException) {
            assertTrue(e.message!!.contains("No API key"))
        }
    }

    @Test
    fun `parses a plain JSON reply`() = runTest {
        val modelJson = """{"part_of_speech":"adjective","meaning":"lasting a short time",
            |"synonyms":["fleeting","transient"],"example_en":"The joy was ephemeral.",
            |"translation":"ಕ್ಷಣಿಕ","example_native":"ಆ ಸಂತೋಷ ಕ್ಷಣಿಕವಾಗಿತ್ತು."}""".trimMargin()
        server.enqueue(MockResponse().setBody(candidateBody(modelJson)))

        val result = provider().lookup("ephemeral")

        assertEquals("ephemeral", result.original)
        assertEquals("ಕ್ಷಣಿಕ", result.translation)
        assertEquals("adjective", result.partOfSpeech)
        assertEquals("fleeting, transient", result.synonyms)
    }

    @Test
    fun `strips markdown code fences before parsing`() = runTest {
        val fenced = "```json\n{\"translation\":\"ನಮಸ್ಕಾರ\",\"meaning\":\"a greeting\"}\n```"
        server.enqueue(MockResponse().setBody(candidateBody(fenced)))

        val result = provider().lookup("hello")

        assertEquals("ನಮಸ್ಕಾರ", result.translation)
    }

    @Test
    fun `synonyms as a plain string is accepted, not just a list`() = runTest {
        val modelJson = """{"translation":"x","synonyms":"quick, fast"}"""
        server.enqueue(MockResponse().setBody(candidateBody(modelJson)))

        val result = provider().lookup("rapid")

        assertEquals("quick, fast", result.synonyms)
    }

    @Test
    fun `missing translation field fails loudly`() = runTest {
        server.enqueue(MockResponse().setBody(candidateBody("""{"meaning":"no translation here"}""")))
        try {
            provider().lookup("x")
            fail("expected LookupFailedException")
        } catch (e: LookupFailedException) {
            assertTrue(e.message!!.contains("No translation"))
        }
    }

    @Test
    fun `401 maps to key-rejected message`() = runTest {
        server.enqueue(MockResponse().setResponseCode(401))
        try {
            provider().lookup("x")
            fail("expected LookupFailedException")
        } catch (e: LookupFailedException) {
            assertTrue(e.message!!.contains("API key rejected"))
        }
    }

    @Test
    fun `429 maps to quota message`() = runTest {
        server.enqueue(MockResponse().setResponseCode(429))
        try {
            provider().lookup("x")
            fail("expected LookupFailedException")
        } catch (e: LookupFailedException) {
            assertTrue(e.message!!.contains("quota"))
        }
    }

    @Test
    fun `404 maps to model-not-found message`() = runTest {
        server.enqueue(MockResponse().setResponseCode(404))
        try {
            provider().lookup("x")
            fail("expected LookupFailedException")
        } catch (e: LookupFailedException) {
            assertTrue(e.message!!.contains("not found"))
        }
    }

    @Test
    fun `unparsable envelope fails with unexpected-format message`() = runTest {
        server.enqueue(MockResponse().setBody("""{"unexpected": true}"""))
        try {
            provider().lookup("x")
            fail("expected LookupFailedException")
        } catch (e: LookupFailedException) {
            assertTrue(e.message!!.contains("Unexpected API response"))
        }
    }
}
