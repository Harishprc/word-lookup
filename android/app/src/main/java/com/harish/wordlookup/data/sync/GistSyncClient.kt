package com.harish.wordlookup.data.sync

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

/**
 * Talks to one private GitHub Gist holding `lookups.json` — the sync blob
 * shared with the desktop app's `kannada_lookup/sync.py`. Auth is a
 * personal access token with only the `gist` scope (no OAuth, no
 * expiring refresh tokens — see the "why a Gist, not Drive" tradeoff in
 * android/README.md).
 *
 * Uses kotlinx.serialization exclusively (not android.jar's `org.json`,
 * which is stub-only on a plain JVM and would force every test through
 * Robolectric) so this class is testable with plain JUnit + MockWebServer.
 *
 * Protocol per sync, mirrored exactly in sync.py: GET the gist → merge
 * locally → PATCH only if the merge changed anything → if the PATCH
 * lands on a gist that moved since the GET (another device wrote in
 * between, HTTP 409), re-GET, re-merge, retry once. Good enough for one
 * person with two devices; not a general-purpose CRDT.
 */
class GistSyncClient(
    private val pat: String,
    private val client: OkHttpClient = defaultClient,
    private val apiBase: String = "https://api.github.com",
) {
    companion object {
        private val JSON_MEDIA_TYPE = "application/json".toMediaType()
        private const val FILENAME = "lookups.json"
        private const val DESCRIPTION = "Word Lookup sync cache (private, auto-managed)"

        val defaultClient: OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(15, TimeUnit.SECONDS)
            .build()

        private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
    }

    class GistSyncException(message: String) : Exception(message)

    @Serializable
    private data class GistFile(val content: String)

    @Serializable
    private data class GistResponse(val id: String = "", val files: Map<String, GistFile> = emptyMap())

    @Serializable
    private data class GistFilePatch(val content: String)

    @Serializable
    private data class GistRequestBody(
        val description: String = DESCRIPTION,
        @SerialName("public") val isPublic: Boolean = false,
        val files: Map<String, GistFilePatch>,
    )

    /** Fetches the payload for an existing gist ID, or null if [gistId]
     * is blank (no gist created yet — the first successful [push] will
     * create one and the caller should remember its ID). */
    suspend fun pull(gistId: String): SyncPayload? = withContext(Dispatchers.IO) {
        if (gistId.isBlank()) return@withContext null
        val request = authedRequest("$apiBase/gists/$gistId").get().build()
        client.newCall(request).execute().use { resp ->
            if (resp.code == 404) return@withContext null
            if (!resp.isSuccessful) throw GistSyncException("Gist fetch failed (${resp.code}).")
            val gist = json.decodeFromString(GistResponse.serializer(), resp.body!!.string())
            val content = gist.files[FILENAME]?.content
                ?: throw GistSyncException("Gist has no $FILENAME file.")
            parsePayload(content)
        }
    }

    /** Creates the gist on first use, or PATCHes the existing one.
     * Returns the (possibly newly created) gist ID. */
    suspend fun push(gistId: String, payload: SyncPayload): String = withContext(Dispatchers.IO) {
        val body = json.encodeToString(
            GistRequestBody(files = mapOf(FILENAME to GistFilePatch(json.encodeToString(payload))))
        )
        val request = if (gistId.isBlank()) {
            authedRequest("$apiBase/gists").post(body.toRequestBody(JSON_MEDIA_TYPE)).build()
        } else {
            authedRequest("$apiBase/gists/$gistId").patch(body.toRequestBody(JSON_MEDIA_TYPE)).build()
        }
        client.newCall(request).execute().use { resp ->
            if (resp.code == 409) throw GistSyncException("Gist changed concurrently — retry.")
            if (!resp.isSuccessful) throw GistSyncException("Gist ${if (gistId.isBlank()) "create" else "update"} failed (${resp.code}).")
            json.decodeFromString(GistResponse.serializer(), resp.body!!.string()).id.ifBlank { gistId }
        }
    }

    private fun parsePayload(content: String): SyncPayload =
        try {
            json.decodeFromString(SyncPayload.serializer(), content)
        } catch (e: Exception) {
            throw GistSyncException("Could not parse sync gist — is lookups.json valid JSON?")
        }

    private fun authedRequest(url: String): Request.Builder {
        if (pat.isBlank()) throw GistSyncException("No GitHub token set — add one in Settings to enable sync.")
        return Request.Builder()
            .url(url)
            .addHeader("Authorization", "Bearer $pat")
            .addHeader("Accept", "application/vnd.github+json")
    }
}
