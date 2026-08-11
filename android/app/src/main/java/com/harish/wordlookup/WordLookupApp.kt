package com.harish.wordlookup

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import com.harish.wordlookup.data.ApiKeyStore
import com.harish.wordlookup.data.GeminiProvider
import com.harish.wordlookup.data.LookupRepository
import com.harish.wordlookup.data.Settings
import com.harish.wordlookup.data.cache.LookupDatabase
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn

/**
 * Composition root — analogue of `App.__init__` in main.py, minus the Qt
 * wiring. Every entry point (ProcessTextActivity, the accessibility
 * service, MainActivity, SyncWorker) reads its dependencies from here
 * rather than constructing its own, so there is exactly one Room instance
 * and one repository per process.
 */
class WordLookupApp : Application() {
    lateinit var settings: Settings
        private set
    lateinit var apiKeyStore: ApiKeyStore
        private set
    lateinit var repository: LookupRepository
        private set

    /** Process-lifetime scope for background collectors — not tied to any
     * screen. Used to keep [enabledState] warm so the accessibility
     * service (which fires from a non-suspend callback) can read the
     * on/off flag synchronously instead of blocking on a DataStore read. */
    private val applicationScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    /** Cached mirror of `settings.enabled`. Source of truth is still
     * DataStore; this just avoids blocking I/O on the accessibility
     * event thread. Three consumers read it: the accessibility service,
     * the QS tile, and MainActivity's toggle — one Flow, matching how
     * `App.enabled` in main.py gates every lookup path. */
    lateinit var enabledState: StateFlow<Boolean>
        private set

    override fun onCreate() {
        super.onCreate()
        settings = Settings(this)
        apiKeyStore = ApiKeyStore(this)
        enabledState = settings.enabled.stateIn(applicationScope, SharingStarted.Eagerly, true)
        val dao = LookupDatabase.get(this).lookupDao()
        repository = LookupRepository(dao, providerFactory = { language ->
            GeminiProvider(
                apiKey = apiKeyStore.geminiApiKey,
                model = apiKeyStore.geminiModel,
                language = language,
            )
        })
        createNotificationChannel()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val channel = NotificationChannel(
            SYNC_CHANNEL_ID,
            "Background sync",
            NotificationManager.IMPORTANCE_MIN,
        )
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    companion object {
        const val SYNC_CHANNEL_ID = "word_lookup_sync"
    }
}
