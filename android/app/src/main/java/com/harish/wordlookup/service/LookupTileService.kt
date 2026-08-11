package com.harish.wordlookup.service

import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import com.harish.wordlookup.R
import com.harish.wordlookup.WordLookupApp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

/**
 * The notification-shade quick toggle the user asked for — drag it into
 * the shade once (Quick Settings edit pencil), then tap to flip the same
 * `enabled` flag the tray "Enabled" checkbox flips on desktop
 * (main.py's `App._toggle`). Path B (PROCESS_TEXT) keeps working even
 * when this is OFF — flipping OFF only silences the instant-overlay path,
 * exactly like the desktop toggle only gates the button-press trigger.
 */
class LookupTileService : TileService() {
    private val scope = CoroutineScope(Dispatchers.Main)
    private var collectJob: Job? = null

    override fun onStartListening() {
        super.onStartListening()
        syncTile((application as WordLookupApp).enabledState.value)
        collectJob = scope.launch {
            (application as WordLookupApp).enabledState.collect { syncTile(it) }
        }
    }

    override fun onStopListening() {
        super.onStopListening()
        collectJob?.cancel()
    }

    override fun onClick() {
        super.onClick()
        val app = application as WordLookupApp
        scope.launch {
            val nowEnabled = app.settings.toggleEnabled()
            syncTile(nowEnabled)
        }
    }

    private fun syncTile(enabled: Boolean) {
        val tile = qsTile ?: return
        tile.state = if (enabled) Tile.STATE_ACTIVE else Tile.STATE_INACTIVE
        tile.label = getString(R.string.tile_label)
        tile.subtitle = if (enabled) "On" else "Off"
        tile.updateTile()
    }
}
