package com.harish.wordlookup.ui

import android.content.Context
import android.graphics.PixelFormat
import android.graphics.Rect
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.WindowManager
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.platform.ComposeView
import androidx.lifecycle.setViewTreeLifecycleOwner
import androidx.lifecycle.setViewTreeViewModelStoreOwner
import androidx.savedstate.setViewTreeSavedStateRegistryOwner

/**
 * Android analogue of `popup.py`'s `LookupPopup`: a floating card that
 * appears at/near a screen position without stealing focus, auto-dismisses
 * after a timeout, and dismisses on tap. Where the desktop version is a
 * frameless always-on-top Qt window, this is a single `WindowManager`
 * overlay window hosting one `ComposeView` — created once, moved and its
 * content swapped for every new lookup, exactly like `LookupPopup` being a
 * "singleton-style popup: each show_* call replaces current contents."
 *
 * Requires the "Display over other apps" permission (`SYSTEM_ALERT_WINDOW`)
 * to have been granted — see MainActivity's permission checklist.
 */
class OverlayHost(private val context: Context) {
    private val windowManager = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
    private val handler = Handler(Looper.getMainLooper())
    private val lifecycleOwner = OverlayLifecycleOwner()
    private val cardState = mutableStateOf<CardState>(CardState.Loading())
    private var composeView: ComposeView? = null
    private var dismissRunnable: Runnable? = null

    /** Auto-dismiss delay — same default as config.POPUP_TIMEOUT_MS. */
    var timeoutMs: Long = 6000

    fun show(state: CardState, anchor: Rect?) {
        cardState.value = state
        ensureViewAttached()
        position(anchor)
        // The view has zero measured size on its very first frame (nothing
        // has laid out yet), so `position` falls back to an estimated
        // width/height. Re-position once real measurements exist so the
        // card doesn't sit slightly off from where `_clamped`-equivalent
        // math intended — the desktop popup never faces this because Qt's
        // `adjustSize()` is synchronous before `move()`.
        composeView?.post { position(anchor) }
        rescheduleDismiss(state)
    }

    fun dismiss() {
        dismissRunnable?.let { handler.removeCallbacks(it) }
        val view = composeView ?: return
        composeView = null
        lifecycleOwner.stop()
        runCatching { windowManager.removeView(view) }
    }

    private fun ensureViewAttached() {
        if (composeView != null) return

        lifecycleOwner.start()
        val view = ComposeView(context).apply {
            setViewTreeLifecycleOwner(lifecycleOwner)
            setViewTreeViewModelStoreOwner(lifecycleOwner)
            setViewTreeSavedStateRegistryOwner(lifecycleOwner)
            setContent {
                val state = cardState.value
                LookupCard(state)
            }
            setOnClickListener { dismiss() }
        }

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.START
        }

        windowManager.addView(view, params)
        composeView = view
    }

    /** Positions below-and-right of the selection bounds, the Android
     * analogue of `popup.py`'s `_clamped` — kept fully on the screen the
     * selection is on rather than sliding off the right/bottom edge. */
    private fun position(anchor: Rect?) {
        val view = composeView ?: return
        val params = view.layoutParams as WindowManager.LayoutParams
        val metrics = context.resources.displayMetrics

        val cardWidth = view.width.takeIf { it > 0 } ?: 340.dpToPx()
        val cardHeight = view.height.takeIf { it > 0 } ?: 120.dpToPx()

        val rawX = anchor?.left ?: (metrics.widthPixels / 2)
        val rawY = anchor?.bottom?.plus(12.dpToPx()) ?: (metrics.heightPixels / 2)

        params.x = rawX.coerceIn(0, (metrics.widthPixels - cardWidth).coerceAtLeast(0))
        params.y = rawY.coerceIn(0, (metrics.heightPixels - cardHeight).coerceAtLeast(0))
        windowManager.updateViewLayout(view, params)
    }

    private fun rescheduleDismiss(state: CardState) {
        dismissRunnable?.let { handler.removeCallbacks(it) }
        // Loading state has no auto-dismiss, matching popup.py's
        // show_loading(timeout_ms=0) — it waits for the real result.
        if (state is CardState.Loading) return
        val runnable = Runnable { dismiss() }
        dismissRunnable = runnable
        handler.postDelayed(runnable, timeoutMs)
    }

    private fun Int.dpToPx(): Int =
        (this * context.resources.displayMetrics.density).toInt()
}
