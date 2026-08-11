package com.harish.wordlookup.service

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.harish.wordlookup.WordLookupApp
import com.harish.wordlookup.data.LookupFailedException
import com.harish.wordlookup.data.LookupRepository
import com.harish.wordlookup.data.Settings
import com.harish.wordlookup.data.TextTruncation
import com.harish.wordlookup.data.sync.SyncWorker
import com.harish.wordlookup.ui.CardState
import com.harish.wordlookup.ui.LookupCard
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

/**
 * Path B (the menu trigger): appears as "Word Lookup" next to Copy / Share
 * whenever text is selected in any app, via the PROCESS_TEXT intent
 * filter. Needs no special permission, so this is the first thing on the
 * phone that's actually usable end-to-end.
 *
 * `Theme.WordLookup.Transparent` (themes.xml) makes the activity a
 * translucent floating host — the OS treats it as a real screen (so it
 * can appear over Chrome/PDF viewers/anything), but visually it's just
 * the card with no background chrome, tap-outside-to-dismiss.
 *
 * Same 500-char cap as config.MAX_CHARS, truncated at a word boundary —
 * PROCESS_TEXT can hand over an entire selected paragraph.
 */
class ProcessTextActivity : ComponentActivity() {

    private val viewModel: LookupViewModel by viewModels {
        object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                val app = application as WordLookupApp
                return LookupViewModel(app.repository, app.settings) as T
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val text = intent?.getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT)?.toString()
        if (text.isNullOrBlank()) {
            finish()
            return
        }
        viewModel.start(TextTruncation.truncate(text))

        setContent {
            val state by viewModel.state.collectAsState()
            // A new lookup is worth syncing eventually — debounced, not
            // immediate, so a burst of quick lookups collapses into one
            // sync instead of firing a job per word.
            LaunchedEffect(state) {
                if (state is CardState.Result) SyncWorker.enqueue(applicationContext)
            }
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(Color.Transparent)
                    .pointerInput(Unit) { detectTapGestures(onTap = { finish() }) }
                    .padding(24.dp),
                contentAlignment = Alignment.TopStart,
            ) {
                LookupCard(state)
            }
        }
    }
}

class LookupViewModel(
    private val repository: LookupRepository,
    private val settings: Settings,
) : ViewModel() {
    private val _state = MutableStateFlow<CardState>(CardState.Loading())
    val state: StateFlow<CardState> = _state

    fun start(text: String) {
        _state.value = CardState.Loading(wordHint = text.take(40))
        viewModelScope.launch {
            val language = settings.targetLanguage.first()
            _state.value = try {
                CardState.Result(repository.lookup(text, language))
            } catch (e: LookupFailedException) {
                CardState.Message(e.message ?: "Lookup failed")
            } catch (e: Exception) {
                CardState.Message("Unexpected error: ${e.message}")
            }
        }
    }
}
