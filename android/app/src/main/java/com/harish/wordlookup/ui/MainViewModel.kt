package com.harish.wordlookup.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.harish.wordlookup.WordLookupApp
import com.harish.wordlookup.data.ApiKeyStore
import com.harish.wordlookup.data.LookupRepository
import com.harish.wordlookup.data.RegisterEntry
import com.harish.wordlookup.data.Settings
import com.harish.wordlookup.data.TriggerMode
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/** Backs MainActivity's screens. Reads Settings/ApiKeyStore/Repository —
 * the same three objects every entry point shares, from WordLookupApp. */
class MainViewModel(
    private val settings: Settings,
    private val apiKeyStore: ApiKeyStore,
    private val repository: LookupRepository,
) : ViewModel() {

    val onboardingDone: StateFlow<Boolean> =
        settings.onboardingDone.stateIn(viewModelScope, SharingStarted.Eagerly, false)

    val targetLanguage: StateFlow<String> =
        settings.targetLanguage.stateIn(viewModelScope, SharingStarted.Eagerly, "Kannada")

    val enabled: StateFlow<Boolean> =
        settings.enabled.stateIn(viewModelScope, SharingStarted.Eagerly, true)

    val triggerMode: StateFlow<TriggerMode> =
        settings.triggerMode.stateIn(viewModelScope, SharingStarted.Eagerly, TriggerMode.BOTH)

    val lastSyncAt: StateFlow<Long?> =
        settings.lastSyncAt.stateIn(viewModelScope, SharingStarted.Eagerly, null)

    val register: StateFlow<List<RegisterEntry>> =
        repository.observeRegister().stateIn(viewModelScope, SharingStarted.Eagerly, emptyList())

    fun hasGeminiKey(): Boolean = apiKeyStore.geminiApiKey.isNotBlank()

    fun saveGeminiKey(key: String) {
        apiKeyStore.geminiApiKey = key
    }

    fun hasGithubPat(): Boolean = apiKeyStore.githubPat.isNotBlank()

    fun saveGithubPat(pat: String) {
        apiKeyStore.githubPat = pat
    }

    fun setLanguage(name: String) = viewModelScope.launch { settings.setTargetLanguage(name) }

    fun setEnabled(value: Boolean) = viewModelScope.launch { settings.setEnabled(value) }

    fun setTriggerMode(mode: TriggerMode) = viewModelScope.launch { settings.setTriggerMode(mode) }

    fun completeOnboarding() = viewModelScope.launch { settings.setOnboardingDone(true) }

    fun deleteWord(language: String, original: String) =
        viewModelScope.launch { repository.delete(language, original) }

    class Factory(private val app: WordLookupApp) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T =
            MainViewModel(app.settings, app.apiKeyStore, app.repository) as T
    }
}
