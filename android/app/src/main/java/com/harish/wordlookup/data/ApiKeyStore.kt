package com.harish.wordlookup.data

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/**
 * Secrets that must never sit in plain DataStore: the Gemini API key and
 * the GitHub PAT used for Gist sync (Phase 7). Desktop equivalent is
 * `.env` (gitignored, plaintext-on-disk-but-off-repo); a phone has no
 * "off repo" equivalent, so this uses Android Keystore-backed encryption
 * instead — a stronger guarantee than the desktop's `.env` file gets.
 */
class ApiKeyStore(context: Context) {
    private val prefs: SharedPreferences by lazy {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            "secure_settings",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    var geminiApiKey: String
        get() = prefs.getString(KEY_GEMINI, "") ?: ""
        set(value) = prefs.edit().putString(KEY_GEMINI, value.trim()).apply()

    var geminiModel: String
        get() = prefs.getString(KEY_MODEL, DEFAULT_MODEL) ?: DEFAULT_MODEL
        set(value) = prefs.edit().putString(KEY_MODEL, value.trim()).apply()

    /** GitHub personal access token, `gist` scope only — see Phase 7. */
    var githubPat: String
        get() = prefs.getString(KEY_GH_PAT, "") ?: ""
        set(value) = prefs.edit().putString(KEY_GH_PAT, value.trim()).apply()

    /** ID of the private gist used as the sync blob; created on first
     * successful sync and remembered so subsequent syncs PATCH the same one. */
    var gistId: String
        get() = prefs.getString(KEY_GIST_ID, "") ?: ""
        set(value) = prefs.edit().putString(KEY_GIST_ID, value.trim()).apply()

    companion object {
        private const val KEY_GEMINI = "gemini_api_key"
        private const val KEY_MODEL = "gemini_model"
        private const val KEY_GH_PAT = "github_pat"
        private const val KEY_GIST_ID = "gist_id"

        // Same alias-tracking default as config.py's GEMINI_MODEL —
        // auto-follows Google's current model instead of a version pin
        // that eventually goes stale.
        //
        // flash, not flash-lite: flash-lite has a higher free daily quota
        // but invents plausible-looking words in low-resource scripts
        // ("restricted" came back as "ಮಿಚ್ಛಿತ / ನಿಯನ್ಶ್ರಿತ" in Kannada, neither
        // a real word). Editable in Settings to trade back if needed.
        const val DEFAULT_MODEL = "gemini-flash-latest"
    }
}
