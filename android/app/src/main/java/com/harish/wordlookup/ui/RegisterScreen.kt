package com.harish.wordlookup.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.harish.wordlookup.data.RegisterEntry
import java.text.DateFormat
import java.util.Date

/**
 * Every lookup ever made, searchable, newest first — Compose equivalent of
 * `register.py`'s generated `register.html`, backed live by Room instead
 * of a static file regenerated on demand.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RegisterScreen(
    entries: List<RegisterEntry>,
    onBack: () -> Unit,
    onDelete: (language: String, original: String) -> Unit,
) {
    var query by remember { mutableStateOf("") }
    val filtered = remember(entries, query) {
        if (query.isBlank()) entries else entries.filter { entry ->
            val r = entry.result
            listOf(r.original, r.meaning, r.synonyms, r.translation)
                .any { it.contains(query, ignoreCase = true) }
        }
    }

    Scaffold(
        topBar = {
            // TopAppBar, not SmallTopAppBar: the latter was deprecated in
            // Material3 1.2 and removed in 1.3 (which the 2024.09 BOM pulls).
            TopAppBar(
                title = { Text("Word register (${entries.size})") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
    ) { padding ->
        Column(modifier = Modifier.fillMaxSize().padding(padding)) {
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                modifier = Modifier.fillMaxWidth().padding(12.dp),
                placeholder = { Text("Search word, meaning, synonym…") },
                singleLine = true,
            )
            if (filtered.isEmpty()) {
                Text(
                    if (entries.isEmpty()) "No lookups yet — select a word anywhere to start."
                    else "No matches.",
                    modifier = Modifier.padding(16.dp),
                )
            }
            LazyColumn {
                items(filtered, key = { it.language + it.result.original }) { entry ->
                    RegisterRow(entry, onDelete)
                    HorizontalDivider()
                }
            }
        }
    }
}

@Composable
private fun RegisterRow(entry: RegisterEntry, onDelete: (String, String) -> Unit) {
    val r = entry.result
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Row {
                Text(r.original, style = MaterialTheme.typography.titleMedium)
                if (r.partOfSpeech.isNotBlank()) {
                    Text(
                        "  · ${r.partOfSpeech}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            if (r.meaning.isNotBlank()) {
                Text(r.meaning, style = MaterialTheme.typography.bodyMedium)
            }
            if (r.synonyms.isNotBlank()) {
                Text(
                    r.synonyms,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Text(r.translation, style = MaterialTheme.typography.titleMedium)
            if (r.exampleNative.isNotBlank()) {
                Text(r.exampleNative, style = MaterialTheme.typography.bodySmall)
            }
            Text(
                "${entry.language} · ${formatDate(entry.createdAtMillis)}",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.outline,
            )
        }
        IconButton(
            onClick = { onDelete(entry.language, r.original) },
            modifier = Modifier.align(Alignment.CenterVertically),
        ) {
            Icon(Icons.Filled.Delete, contentDescription = "Delete")
        }
    }
}

private fun formatDate(epochMillis: Long): String =
    DateFormat.getDateInstance(DateFormat.MEDIUM).format(Date(epochMillis))
