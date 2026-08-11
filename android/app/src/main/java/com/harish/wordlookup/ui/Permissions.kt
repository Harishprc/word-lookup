package com.harish.wordlookup.ui

import android.app.StatusBarManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.graphics.drawable.Icon
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.text.TextUtils
import com.harish.wordlookup.R
import com.harish.wordlookup.service.LookupTileService
import java.util.concurrent.Executor
import java.util.function.Consumer

/**
 * Permission status + deep-link helpers for the checklist screen. Nothing
 * here can *grant* a permission — Android deliberately requires the user
 * to flip these in the system Settings app, not a dialog inside ours; the
 * best this app can do is check status and jump straight to the right
 * settings screen.
 */
object Permissions {

    fun hasOverlay(context: Context): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(context)

    fun overlayIntent(context: Context): Intent =
        Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:${context.packageName}"))

    /** No official API for "is my AccessibilityService enabled" beyond
     * parsing the same colon-separated settings string the system uses
     * internally — this is the standard approach every accessibility app
     * uses, not a hack specific to this app. */
    fun hasAccessibilityServiceEnabled(context: Context, serviceClassName: String): Boolean {
        val enabledServices = Settings.Secure.getString(
            context.contentResolver,
            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
        ) ?: return false
        val expected = "${context.packageName}/$serviceClassName"
        val splitter = TextUtils.SimpleStringSplitter(':')
        splitter.setString(enabledServices)
        for (component in splitter) {
            if (component.equals(expected, ignoreCase = true)) return true
        }
        return false
    }

    fun accessibilitySettingsIntent(): Intent =
        Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)

    /**
     * Ask the system to add the Quick Settings tile, showing the standard
     * "Add tile?" dialog. Android 13 (TIRAMISU) added this; before it, an
     * app had no way to place its own tile and the user had to find it in
     * the Quick Settings edit screen by hand — which is exactly what gets
     * missed, since nothing in the UI hints the tile exists.
     *
     * Returns false when the platform is too old to ask, so the caller can
     * fall back to printed instructions.
     */
    fun requestAddTile(context: Context, onResult: (Int) -> Unit): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return false
        val statusBar = context.getSystemService(StatusBarManager::class.java) ?: return false
        // Executor and Consumer are spelled out rather than passed as bare
        // lambdas: Kotlin SAM-converts a literal, but `onResult` is already
        // a function-typed value, and those do not implicitly convert to a
        // Java functional interface.
        statusBar.requestAddTileService(
            ComponentName(context, LookupTileService::class.java),
            context.getString(R.string.tile_label),
            Icon.createWithResource(context, R.drawable.ic_tile),
            Executor { it.run() },
            Consumer { result -> onResult(result) },
        )
        return true
    }

    /** Deep-links to this app's own App Info page — where the Android 13+
     * "Allow restricted settings" toggle lives (⋮ menu, top right). There
     * is no direct intent action for that menu item itself. */
    fun appInfoIntent(context: Context): Intent =
        Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${context.packageName}"))

    fun needsNotificationRuntimePermission(): Boolean =
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
}
