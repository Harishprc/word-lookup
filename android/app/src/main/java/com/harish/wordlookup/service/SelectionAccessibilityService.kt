package com.harish.wordlookup.service

import android.accessibilityservice.AccessibilityService
import android.graphics.Rect
import android.os.Handler
import android.os.Looper
import android.view.accessibility.AccessibilityEvent
import com.harish.wordlookup.WordLookupApp
import com.harish.wordlookup.data.LookupFailedException
import com.harish.wordlookup.data.TextTruncation
import com.harish.wordlookup.ui.CardState
import com.harish.wordlookup.ui.OverlayHost
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

/**
 * Path A (the instant trigger): fires an overlay card the moment text is
 * selected in any app, no tap needed. Android's only real-time signal for
 * "text was selected" is `TYPE_VIEW_TEXT_SELECTION_CHANGED`, which only an
 * AccessibilityService receives — this is why the app needs the
 * Accessibility permission for this path at all.
 *
 * Must be enabled by hand in Settings > Accessibility; on Android 13+ a
 * sideloaded app also needs "Allow restricted settings" tapped first on
 * its App Info page before the toggle will even work (see MainActivity's
 * permission checklist and the README).
 */
class SelectionAccessibilityService : AccessibilityService() {

    private lateinit var overlay: OverlayHost
    private lateinit var app: WordLookupApp
    private val mainHandler = Handler(Looper.getMainLooper())
    private val scope = CoroutineScope(Dispatchers.Main)
    private var lookupJob: Job? = null

    // Debounce: mirrors config.DEBOUNCE_S (0.3s) — stops rapid re-fires
    // while a user drags a selection handle across a paragraph.
    private var lastFireAt = 0L
    private var lastQuery: String? = null
    private val debounceMs = 300L

    override fun onCreate() {
        super.onCreate()
        app = application as WordLookupApp
        overlay = OverlayHost(this)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        event ?: return
        if (event.eventType != AccessibilityEvent.TYPE_VIEW_TEXT_SELECTION_CHANGED) return

        // First line of the handler, matching main.py's App.enabled gate —
        // an OFF toggle must cost nothing, not even a text read. Reads the
        // cached StateFlow (see WordLookupApp.enabledState), never blocks.
        if (!app.enabledState.value) return

        // Never look inside our own overlay or a password/edit-in-progress
        // field — the latter is "typing", not "selecting to look up".
        if (event.packageName == packageName) return
        val source = event.source
        if (source?.isPassword == true) return

        val start = event.fromIndex
        val end = event.toIndex
        if (start < 0 || end < 0 || start == end) return // caret move, not a selection

        val text = extractSelection(event, source, start, end) ?: return
        if (text.isBlank()) return

        val now = System.currentTimeMillis()
        if (text == lastQuery && now - lastFireAt < debounceMs) return
        lastFireAt = now
        lastQuery = text

        val bounds = Rect().also { source?.getBoundsInScreen(it) }
        fireLookup(TextTruncation.truncate(text), bounds.takeIf { !it.isEmpty })
    }

    /** event.text first (cheap, present for most standard widgets), else
     * fall back to reading the source node's full text and slicing by the
     * reported selection range — WebView/Compose selections often only
     * populate the second path. */
    private fun extractSelection(
        event: AccessibilityEvent,
        source: android.view.accessibility.AccessibilityNodeInfo?,
        start: Int,
        end: Int,
    ): String? {
        val fromEvent = event.text?.joinToString("")?.takeIf { it.isNotBlank() }
        if (fromEvent != null) return fromEvent

        val full = source?.text?.toString() ?: return null
        val lo = start.coerceIn(0, full.length)
        val hi = end.coerceIn(0, full.length)
        if (lo == hi) return null
        return full.substring(minOf(lo, hi), maxOf(lo, hi))
    }

    private fun fireLookup(text: String, bounds: Rect?) {
        lookupJob?.cancel()
        overlay.show(CardState.Loading(wordHint = text.take(40)), bounds)
        lookupJob = scope.launch {
            val language = app.settings.targetLanguage.first()
            val state = try {
                CardState.Result(app.repository.lookup(text, language)).also {
                    // Debounced — see SyncWorker.enqueue's kdoc.
                    com.harish.wordlookup.data.sync.SyncWorker.enqueue(this@SelectionAccessibilityService)
                }
            } catch (e: LookupFailedException) {
                CardState.Message(e.message ?: "Lookup failed")
            } catch (e: Exception) {
                CardState.Message("Unexpected error: ${e.message}")
            }
            overlay.show(state, bounds)
        }
    }

    override fun onInterrupt() {
        overlay.dismiss()
    }

    override fun onDestroy() {
        super.onDestroy()
        lookupJob?.cancel()
        overlay.dismiss()
    }
}
