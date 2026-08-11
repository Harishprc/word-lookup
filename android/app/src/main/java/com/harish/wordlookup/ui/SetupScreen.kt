package com.harish.wordlookup.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.harish.wordlookup.data.Languages

/**
 * First-run setup — mirrors `setup_dialog.py`: pick a target language,
 * paste a Gemini key. Both are the one-time answers that unlock every
 * other screen (`onboardingDone`), same role as `data/settings.json`'s
 * absence being the desktop app's first-run signal.
 */
@Composable
fun SetupScreen(
    initialLanguage: String,
    // True when reopened from Settings to edit an already-configured
    // install — leaving a key field blank then just keeps the existing
    // key instead of blocking the Continue button.
    keyAlreadySet: Boolean = false,
    githubPatAlreadySet: Boolean = false,
    onSave: (language: String, apiKey: String, githubPat: String) -> Unit,
) {
    var language by remember { mutableStateOf(initialLanguage) }
    var apiKey by remember { mutableStateOf("") }
    var githubPat by remember { mutableStateOf("") }
    var expanded by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Welcome to Word Lookup", style = MaterialTheme.typography.headlineSmall)
        Text(
            "Select text in any app and see a dictionary card — meaning, " +
                "synonyms, an example, and the translation you pick below.",
            style = MaterialTheme.typography.bodyMedium,
        )

        Text("Target language", style = MaterialTheme.typography.titleSmall)
        Box {
            OutlinedTextField(
                value = language,
                onValueChange = {},
                readOnly = true,
                modifier = Modifier.fillMaxWidth(),
                trailingIcon = {
                    IconButton(onClick = { expanded = true }) {
                        Icon(Icons.Filled.ArrowDropDown, contentDescription = "Choose language")
                    }
                },
            )
            DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                Languages.ALL.forEach { entry ->
                    DropdownMenuItem(
                        text = { Text("${entry.glyph}  ${entry.name}") },
                        onClick = { language = entry.name; expanded = false },
                    )
                }
            }
        }

        Text("Gemini API key", style = MaterialTheme.typography.titleSmall)
        Text(
            "Free, no credit card — aistudio.google.com → \"Get API key\". " +
                "Roughly 1,500 lookups/day on the free tier.",
            style = MaterialTheme.typography.bodySmall,
        )
        OutlinedTextField(
            value = apiKey,
            onValueChange = { apiKey = it },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            placeholder = { Text(if (keyAlreadySet) "Leave blank to keep the current key" else "Paste your key") },
        )

        Text("GitHub token (optional — enables sync)", style = MaterialTheme.typography.titleSmall)
        Text(
            "github.com/settings/tokens → generate one with only the \"gist\" " +
                "scope. Syncs this phone's cache with the desktop app's, via " +
                "one private Gist. Skip this and sync stays off.",
            style = MaterialTheme.typography.bodySmall,
        )
        OutlinedTextField(
            value = githubPat,
            onValueChange = { githubPat = it },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            placeholder = {
                Text(if (githubPatAlreadySet) "Leave blank to keep the current token" else "Optional")
            },
        )

        Button(
            onClick = { onSave(language, apiKey, githubPat) },
            enabled = apiKey.isNotBlank() || keyAlreadySet,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Continue")
        }

        Text(
            "You can change any of this later from the main screen. Both keys " +
                "are encrypted on-device — the Gemini key only goes to Google's " +
                "API, the GitHub token only to your own private Gist.",
            style = MaterialTheme.typography.bodySmall,
        )
    }
}
