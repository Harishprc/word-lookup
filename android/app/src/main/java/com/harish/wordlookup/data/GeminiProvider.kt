package com.harish.wordlookup.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * Gemini API (AI Studio key) — full dictionary card in one call.
 *
 * Direct Kotlin port of `kannada_lookup/translator.py`'s `GeminiProvider`:
 * same endpoint, same prompt (copied verbatim — it's tuned, and the two
 * apps should return identical cards for the same word), same status-code
 * error messages, same ```json-fence-tolerant parsing, same synonyms
 * list-or-string coercion.
 */
class GeminiProvider(
    private val apiKey: String,
    private val model: String,
    private val language: String,
    private val client: OkHttpClient = defaultClient,
    // Overridable so tests can point at a MockWebServer instead of the
    // real Gemini host; production callers never pass this.
    private val endpointTemplate: String = DEFAULT_ENDPOINT_TEMPLATE,
) {
    companion object {
        const val DEFAULT_ENDPOINT_TEMPLATE =
            "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"

        val defaultClient: OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(10, TimeUnit.SECONDS)
            .build()

        private val JSON_MEDIA_TYPE = "application/json".toMediaType()

        // Verbatim from translator.py's _PROMPT — do not reword
        // independently of the desktop prompt, the two must stay in
        // lockstep (identical cards for the same word, one shared cache).
        //
        // The translation rules exist because weaker models invent
        // plausible-looking words in low-resource scripts: asking for
        // "restricted" in Kannada produced "ಮಿಚ್ಛಿತ / ನಿಯನ್ಶ್ರಿತ" — neither is
        // a real word, and the second is a malformed consonant cluster
        // that renders with a dotted circle (the Unicode
        // orphaned-combining-mark marker). Naming the failure modes
        // explicitly is what suppresses them.
        private fun prompt(language: String, text: String): String =
            "You are an English-$language dictionary. For the English word or " +
                "phrase below, reply with ONLY this JSON:\n" +
                "{\"part_of_speech\": \"<noun/verb/adjective/adverb/…, or empty for " +
                "multi-word phrases>\", " +
                "\"meaning\": \"<short, plain English meaning>\", " +
                "\"synonyms\": [\"<2-3 synonyms common in conversational English>\"], " +
                "\"example_en\": \"<one short, simple example sentence in English " +
                "that uses the word>\", " +
                "\"translation\": \"<the $language translation>\", " +
                "\"example_native\": \"<one short, simple example sentence written in " +
                "$language that uses that word>\"}\n" +
                "For multi-word phrases, synonyms may be an empty list.\n\n" +
                "Rules for the $language text:\n" +
                "- Give exactly ONE translation: the single most commonly used " +
                "word. Never offer alternatives, and never use a slash.\n" +
                "- It must be a real, standard $language word that a native " +
                "speaker would recognise and a dictionary would list. If no true " +
                "equivalent exists, use the ordinary $language phrase for the " +
                "idea rather than inventing a word.\n" +
                "- Write it in correct, well-formed $language script. Never " +
                "spell the English word out phonetically in that script.\n" +
                "- Use only valid letter combinations for $language. Do not " +
                "produce malformed clusters.\n\n" +
                "English: $text"
    }

    suspend fun lookup(text: String): LookupResult = withContext(Dispatchers.IO) {
        if (apiKey.isBlank()) {
            throw LookupFailedException(
                "No API key. Get a free one at aistudio.google.com and set it in Settings."
            )
        }

        val body = JsonObject(
            mapOf(
                "contents" to JsonArray(
                    listOf(
                        JsonObject(
                            mapOf(
                                "role" to JsonPrimitive("user"),
                                "parts" to JsonArray(
                                    listOf(
                                        JsonObject(
                                            mapOf("text" to JsonPrimitive(prompt(language, text)))
                                        )
                                    )
                                ),
                            )
                        )
                    )
                ),
                // Forces raw JSON output — no prose, no markdown fences
                // (fences still tolerated below, belt and suspenders).
                "generationConfig" to JsonObject(
                    mapOf("responseMimeType" to JsonPrimitive("application/json"))
                ),
            )
        ).toString()

        val request = Request.Builder()
            .url(endpointTemplate.format(model))
            .addHeader("x-goog-api-key", apiKey)
            .post(body.toRequestBody(JSON_MEDIA_TYPE))
            .build()

        val response = try {
            client.newCall(request).execute()
        } catch (e: java.net.SocketTimeoutException) {
            throw LookupFailedException("Lookup timed out — check your connection.")
        } catch (e: IOException) {
            throw LookupFailedException("No internet connection.")
        }

        response.use { resp ->
            when (resp.code) {
                400, 401, 403 -> throw LookupFailedException(
                    "API key rejected (${resp.code}). Check the key in Settings."
                )
                429 -> throw LookupFailedException(
                    "Free-tier quota hit (~1,500/day). Wait a minute or try tomorrow."
                )
                404 -> throw LookupFailedException(
                    "Model '$model' not found — check GEMINI_MODEL in Settings " +
                        "(e.g. gemini-flash-lite-latest)."
                )
            }
            if (!resp.isSuccessful) {
                throw LookupFailedException("Gemini API error ${resp.code}.")
            }

            val raw = try {
                val json = Json.parseToJsonElement(resp.body!!.string()).jsonObject
                json["candidates"]!!.jsonArray[0].jsonObject["content"]!!
                    .jsonObject["parts"]!!.jsonArray[0].jsonObject["text"]!!.jsonPrimitive.content
            } catch (e: Exception) {
                throw LookupFailedException("Unexpected API response format.")
            }

            val data = parseModelJson(raw)
            val translation = (data["translation"] as? JsonPrimitive)?.content?.trim().orEmpty()
            if (translation.isEmpty()) {
                throw LookupFailedException("No translation returned — try again.")
            }

            return@use LookupResult(
                original = text,
                translation = translation,
                partOfSpeech = stringField(data, "part_of_speech").lowercase(),
                meaning = stringField(data, "meaning"),
                synonyms = synonymsField(data),
                exampleEn = stringField(data, "example_en"),
                exampleNative = stringField(data, "example_native"),
            )
        }
    }

    /** Parse model output; tolerate ```json fences some models emit —
     * mirrors translator.py's `_parse_json`. */
    private fun parseModelJson(raw: String): JsonObject {
        var cleaned = raw.trim()
        if (cleaned.startsWith("```")) {
            cleaned = cleaned.substringAfter("\n", cleaned)
            cleaned = cleaned.substringBeforeLast("```")
        }
        return try {
            Json.parseToJsonElement(cleaned).jsonObject
        } catch (e: Exception) {
            throw LookupFailedException("Could not read model reply — try again.")
        }
    }

    private fun stringField(obj: JsonObject, key: String): String =
        (obj[key] as? JsonPrimitive)?.content?.trim().orEmpty()

    /** Model may return synonyms as a JSON array or a plain string — accept
     * either, same as translator.py:143-145. */
    private fun synonymsField(obj: JsonObject): String {
        val element: JsonElement = obj["synonyms"] ?: return ""
        return if (element is JsonArray) {
            element.jsonArray
                .mapNotNull { (it as? JsonPrimitive)?.content?.trim() }
                .filter { it.isNotEmpty() }
                .joinToString(", ")
        } else {
            (element as? JsonPrimitive)?.content?.trim().orEmpty()
        }
    }
}
