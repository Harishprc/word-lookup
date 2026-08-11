package com.harish.wordlookup.ui

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import com.harish.wordlookup.WordLookupApp
import com.harish.wordlookup.data.TriggerMode
import com.harish.wordlookup.data.sync.SyncWorker
import com.harish.wordlookup.service.SelectionAccessibilityService

/**
 * Single-Activity host for onboarding, the permission checklist, settings,
 * and the register — no navigation-compose dependency, just a small
 * in-memory screen switch, since the whole app is four screens deep at
 * most.
 */
class MainActivity : ComponentActivity() {

    private val viewModel: MainViewModel by viewModels {
        MainViewModel.Factory(application as WordLookupApp)
    }

    private val requestNotifications =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { /* no-op: re-read on resume */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface {
                    val onboardingDone by viewModel.onboardingDone.collectAsState()
                    if (!onboardingDone) {
                        val language by viewModel.targetLanguage.collectAsState()
                        SetupScreen(initialLanguage = language) { lang, key, pat ->
                            viewModel.setLanguage(lang)
                            viewModel.saveGeminiKey(key)
                            if (pat.isNotBlank()) viewModel.saveGithubPat(pat)
                            viewModel.completeOnboarding()
                        }
                    } else {
                        var screen by remember { mutableStateOf(Screen.HOME) }
                        when (screen) {
                            Screen.HOME -> HomeScreen(
                                viewModel = viewModel,
                                onOpenRegister = { screen = Screen.REGISTER },
                                onOpenSettings = { screen = Screen.SETTINGS },
                                onRequestNotificationPermission = {
                                    requestNotifications.launch(Manifest.permission.POST_NOTIFICATIONS)
                                },
                            )
                            Screen.REGISTER -> {
                                val entries by viewModel.register.collectAsState()
                                RegisterScreen(
                                    entries = entries,
                                    onBack = { screen = Screen.HOME },
                                    onDelete = viewModel::deleteWord,
                                )
                            }
                            Screen.SETTINGS -> {
                                val language by viewModel.targetLanguage.collectAsState()
                                SetupScreen(
                                    initialLanguage = language,
                                    keyAlreadySet = viewModel.hasGeminiKey(),
                                    githubPatAlreadySet = viewModel.hasGithubPat(),
                                ) { lang, key, pat ->
                                    viewModel.setLanguage(lang)
                                    if (key.isNotBlank()) viewModel.saveGeminiKey(key)
                                    if (pat.isNotBlank()) viewModel.saveGithubPat(pat)
                                    screen = Screen.HOME
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

private enum class Screen { HOME, REGISTER, SETTINGS }

@Composable
private fun HomeScreen(
    viewModel: MainViewModel,
    onOpenRegister: () -> Unit,
    onRequestNotificationPermission: () -> Unit,
    onOpenSettings: () -> Unit = {},
) {
    val context = LocalContext.current
    val enabled by viewModel.enabled.collectAsState()
    val language by viewModel.targetLanguage.collectAsState()
    val triggerMode by viewModel.triggerMode.collectAsState()
    val lastSyncAt by viewModel.lastSyncAt.collectAsState()

    // Permission status can only change while this screen isn't in the
    // foreground (the user is off in system Settings granting it), so
    // re-check on every resume rather than once at composition.
    var overlayGranted by remember { mutableStateOf(Permissions.hasOverlay(context)) }
    var accessibilityGranted by remember {
        mutableStateOf(
            Permissions.hasAccessibilityServiceEnabled(
                context, SelectionAccessibilityService::class.java.name,
            )
        )
    }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) {
        overlayGranted = Permissions.hasOverlay(context)
        accessibilityGranted = Permissions.hasAccessibilityServiceEnabled(
            context, SelectionAccessibilityService::class.java.name,
        )
    }

    LaunchedEffect(Unit) {
        if (Permissions.needsNotificationRuntimePermission() &&
            context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            onRequestNotificationPermission()
        }
        // Opening the app is a reasonable "probably online, probably a
        // good moment" signal — sync promptly rather than waiting for the
        // post-lookup debounce. Still gated by the CONNECTED constraint.
        SyncWorker.enqueueNow(context)
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column {
                Text("Word Lookup", style = MaterialTheme.typography.headlineSmall)
                Text(
                    "Target: $language",
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
            Switch(checked = enabled, onCheckedChange = viewModel::setEnabled)
        }

        OutlinedButton(onClick = onOpenSettings) { Text("Change language / API key") }

        SectionCard(title = "Permissions") {
            PermissionRow(
                label = "Display over other apps",
                detail = "Needed to show the instant card as an overlay.",
                granted = overlayGranted,
                actionLabel = if (overlayGranted) "Granted" else "Open Settings",
            ) { context.startActivity(Permissions.overlayIntent(context)) }

            HorizontalDivider()

            PermissionRow(
                label = "Accessibility service",
                detail = "Needed for the instant (no-tap) trigger. On Android 13+, " +
                    "first open App Info (below) → ⋮ → \"Allow restricted settings\", " +
                    "then enable it here.",
                granted = accessibilityGranted,
                actionLabel = if (accessibilityGranted) "Granted" else "Open Settings",
            ) { context.startActivity(Permissions.accessibilitySettingsIntent()) }

            if (!accessibilityGranted) {
                OutlinedButton(onClick = { context.startActivity(Permissions.appInfoIntent(context)) }) {
                    Text("Open App Info (for \"Allow restricted settings\")")
                }
            }
        }

        // Without this the tile is effectively invisible: Android never
        // places a third-party tile automatically, and nothing in the shade
        // hints that one is available to add.
        SectionCard(title = "Quick Settings tile") {
            Text(
                "Puts an on/off toggle in the notification shade.",
                style = MaterialTheme.typography.bodyMedium,
            )
            OutlinedButton(onClick = {
                val asked = Permissions.requestAddTile(context) { }
                if (!asked) {
                    Toast.makeText(
                        context,
                        "Open Quick Settings → pencil (edit) → drag \"Word Lookup\" in.",
                        Toast.LENGTH_LONG,
                    ).show()
                }
            }) { Text("Add tile to Quick Settings") }
            Text(
                "If the dialog doesn't appear, add it by hand: open Quick " +
                    "Settings, tap the pencil (edit), then drag \"Word Lookup\" " +
                    "into the panel.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        SectionCard(title = "Trigger") {
            TriggerMode.entries.forEach { mode ->
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
                ) {
                    RadioButton(
                        selected = triggerMode == mode,
                        onClick = { viewModel.setTriggerMode(mode) },
                    )
                    Text(mode.label())
                }
            }
        }

        SectionCard(title = "Word register") {
            Text("Every lookup you've made, searchable, newest first.")
            Button(onClick = onOpenRegister) { Text("Open register") }
        }

        SectionCard(title = "Sync") {
            Text(
                if (lastSyncAt != null) "Last synced: ${formatSyncTime(lastSyncAt)}"
                else "Not synced yet.",
            )
            Text(
                "Syncs automatically when connected. Add a GitHub token " +
                    "(\"gist\" scope only) in Settings to enable it.",
                style = MaterialTheme.typography.bodySmall,
            )
            Button(onClick = { SyncWorker.enqueueNow(context) }) { Text("Sync now") }
        }
    }
}

@Composable
private fun SectionCard(title: String, content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            content()
        }
    }
}

@Composable
private fun PermissionRow(
    label: String,
    detail: String,
    granted: Boolean,
    actionLabel: String,
    onClick: () -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(label, style = MaterialTheme.typography.bodyLarge)
            Text(detail, style = MaterialTheme.typography.bodySmall)
        }
        if (granted) {
            FilterChip(selected = true, onClick = {}, label = { Text("On") })
        } else {
            Button(onClick = onClick) { Text(actionLabel) }
        }
    }
}

private fun TriggerMode.label(): String = when (this) {
    TriggerMode.INSTANT -> "Instant (accessibility overlay)"
    TriggerMode.MENU_ONLY -> "Menu only (no permissions needed)"
    TriggerMode.BOTH -> "Both (recommended)"
}

private fun formatSyncTime(epochMillis: Long?): String {
    epochMillis ?: return "never"
    return java.text.DateFormat.getDateTimeInstance(
        java.text.DateFormat.MEDIUM, java.text.DateFormat.SHORT,
    ).format(java.util.Date(epochMillis))
}
