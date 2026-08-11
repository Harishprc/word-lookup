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
        // StateFlow replays its current value to a new collector, so this
        // single collect covers both the initial paint and later changes.
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

        // Paint the new state synchronously, BEFORE persisting. qsTile is
        // only valid while the tile is in the listening window, and the
        // DataStore write below is asynchronous — if the system stops
        // listening first (common: the shade closes on tap), a post-write
        // updateTile() silently no-ops and the tile looks stuck.
        val next = !app.enabledState.value
        syncTile(next)

        scope.launch {
            // Absolute set, not toggle: two fast taps would otherwise both
            // read the same stale value and cancel each other out.
            app.settings.setEnabled(next)
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
