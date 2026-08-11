package com.harish.wordlookup.ui

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.text.TextUtils

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

    /** Deep-links to this app's own App Info page — where the Android 13+
     * "Allow restricted settings" toggle lives (⋮ menu, top right). There
     * is no direct intent action for that menu item itself. */
    fun appInfoIntent(context: Context): Intent =
        Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${context.packageName}"))

    fun needsNotificationRuntimePermission(): Boolean =
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
}
