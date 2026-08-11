package com.harish.wordlookup.data

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "settings")

/** Which trigger path(s) are active. Menu (PROCESS_TEXT) needs no
 * permission and always works; Instant needs Accessibility + overlay. */
enum class TriggerMode { INSTANT, MENU_ONLY, BOTH }

/**
 * User choices — DataStore analogue of `data/settings.json`. The `enabled`
 * flag here is the single source of truth read by the accessibility
 * service, the QS tile, and the main screen's toggle (three consumers, one
 * Flow), matching how `App.enabled` in main.py gates every lookup path.
 */
class Settings(private val context: Context) {
    private object Keys {
        val TARGET_LANGUAGE = stringPreferencesKey("target_language")
        val ENABLED = booleanPreferencesKey("enabled")
        val TRIGGER_MODE = stringPreferencesKey("trigger_mode")
        val LAST_SYNC_AT = longPreferencesKey("last_sync_at")
        val ONBOARDING_DONE = booleanPreferencesKey("onboarding_done")
    }

    val targetLanguage: Flow<String> = context.dataStore.data.map {
        it[Keys.TARGET_LANGUAGE] ?: Languages.DEFAULT.name
    }

    val enabled: Flow<Boolean> = context.dataStore.data.map { it[Keys.ENABLED] ?: true }

    val triggerMode: Flow<TriggerMode> = context.dataStore.data.map {
        runCatching { TriggerMode.valueOf(it[Keys.TRIGGER_MODE] ?: "") }.getOrDefault(TriggerMode.BOTH)
    }

    val lastSyncAt: Flow<Long?> = context.dataStore.data.map { it[Keys.LAST_SYNC_AT] }

    val onboardingDone: Flow<Boolean> = context.dataStore.data.map { it[Keys.ONBOARDING_DONE] ?: false }

    suspend fun setTargetLanguage(name: String) {
        context.dataStore.edit { it[Keys.TARGET_LANGUAGE] = name }
    }

    suspend fun setEnabled(value: Boolean) {
        context.dataStore.edit { it[Keys.ENABLED] = value }
    }

    suspend fun toggleEnabled(): Boolean {
        var newValue = true
        context.dataStore.edit { prefs ->
            newValue = !(prefs[Keys.ENABLED] ?: true)
            prefs[Keys.ENABLED] = newValue
        }
        return newValue
    }

    suspend fun setTriggerMode(mode: TriggerMode) {
        context.dataStore.edit { it[Keys.TRIGGER_MODE] = mode.name }
    }

    suspend fun setLastSyncAt(epochMillis: Long) {
        context.dataStore.edit { it[Keys.LAST_SYNC_AT] = epochMillis }
    }

    suspend fun setOnboardingDone(value: Boolean) {
        context.dataStore.edit { it[Keys.ONBOARDING_DONE] = value }
    }
}
