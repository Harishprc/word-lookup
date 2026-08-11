package com.harish.wordlookup.data.sync

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import com.harish.wordlookup.WordLookupApp
import com.harish.wordlookup.data.cache.LookupDatabase
import java.util.concurrent.TimeUnit

/**
 * Pushes/pulls the sync Gist, constrained to `NetworkType.CONNECTED` —
 * that constraint *is* the "only sync when connected" behavior: WorkManager
 * holds the job until there's a real connection and batches it with other
 * system wakeups rather than polling, so this costs near-zero battery.
 *
 * Enqueued as unique work (`ExistingWorkPolicy.REPLACE`) so rapid repeat
 * triggers (app open right after a lookup) collapse into one run instead
 * of piling up, mirroring the desktop's debounced tray "Sync now."
 */
class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val app = applicationContext as WordLookupApp
        val pat = app.apiKeyStore.githubPat
        if (pat.isBlank()) return Result.success(workDataOf("skipped" to "no_token"))

        val dao = LookupDatabase.get(app).lookupDao()
        val client = GistSyncClient(pat)

        return try {
            val localEntities = dao.allIncludingDeleted()
            val local = localEntities.map { SyncEntry.fromEntity(it) }

            val gistId = app.apiKeyStore.gistId
            val remotePayload = client.pull(gistId)
            val remote = remotePayload?.entries.orEmpty()

            val merged = SyncMerger.merge(local, remote)

            // Only write back if the merge actually changed something —
            // avoids a pointless PATCH (and gist revision-history churn)
            // on every sync when nothing new happened on either side.
            if (remotePayload == null || !sameContent(merged, remote)) {
                val newGistId = client.push(gistId, SyncPayload(entries = merged))
                if (newGistId != gistId) app.apiKeyStore.gistId = newGistId
            }

            dao.upsertAll(merged.map { it.toEntity() })
            app.settings.setLastSyncAt(System.currentTimeMillis())

            Result.success()
        } catch (e: GistSyncClient.GistSyncException) {
            // Sync never blocks or breaks a lookup — retry next cycle.
            Result.retry()
        } catch (e: Exception) {
            Result.retry()
        }
    }

    private fun sameContent(a: List<SyncEntry>, b: List<SyncEntry>): Boolean =
        a.toSet() == b.toSet()

    companion object {
        private const val UNIQUE_WORK_NAME = "word_lookup_sync"

        /** Called on app open and, debounced, after a new lookup. */
        fun enqueue(context: Context) {
            val request = OneTimeWorkRequestBuilder<SyncWorker>()
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .setInitialDelay(15, TimeUnit.MINUTES) // debounce: coalesce bursts of lookups
                .build()
            WorkManager.getInstance(context)
                .enqueueUniqueWork(UNIQUE_WORK_NAME, ExistingWorkPolicy.REPLACE, request)
        }

        /** Immediate sync — the manual "Sync now" button, no debounce. */
        fun enqueueNow(context: Context) {
            val request = OneTimeWorkRequestBuilder<SyncWorker>()
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .build()
            WorkManager.getInstance(context)
                .enqueueUniqueWork(UNIQUE_WORK_NAME, ExistingWorkPolicy.REPLACE, request)
        }
    }
}
