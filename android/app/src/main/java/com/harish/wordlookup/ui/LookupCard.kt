package com.harish.wordlookup.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.harish.wordlookup.data.LookupResult

/**
 * The card content. One state machine, three renderings — mirrors
 * `popup.py`'s `show_loading` / `show_result` / `show_message`. Used by
 * both the PROCESS_TEXT dialog (Phase 2) and the instant overlay
 * (Phase 3), so trigger path never affects what the user sees.
 *
 * Colors and layout are a direct match to popup.py's `_STYLE` and
 * `_set_texts`: off-white-to-faint-blue gradient, rounded corners, rows
 * collapse when their field is empty, divider only shows when both the
 * English half and the native half have content.
 */
sealed interface CardState {
    data class Loading(val wordHint: String = "") : CardState
    data class Result(val result: LookupResult) : CardState
    data class Message(val text: String) : CardState
}

private val CardTop = Color(0xFFFDFDFE)
private val CardBottom = Color(0xFFEDF2FB)
private val WordColor = Color(0xFF1A1A1A)
private val PosColor = Color(0xFF8A8F9C)
private val MeaningColor = Color(0xFF333333)
private val SynonymsColor = Color(0xFF6A6A6A)
private val DividerColor = Color(0xFFE2E7F0)
private val TranslationColor = Color(0xFF111111)
private val ExampleColor = Color(0xFF555555)

@Composable
fun LookupCard(state: CardState, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier
            .widthIn(max = 340.dp)
            .shadow(elevation = 12.dp, shape = RoundedCornerShape(12.dp), clip = false),
        shape = RoundedCornerShape(12.dp),
        color = Color.Transparent,
    ) {
        Column(
            modifier = Modifier
                .background(
                    Brush.verticalGradient(listOf(CardTop, CardBottom)),
                    RoundedCornerShape(12.dp),
                )
                .padding(horizontal = 16.dp, vertical = 12.dp),
        ) {
            when (state) {
                is CardState.Loading -> LoadingContent(state.wordHint)
                is CardState.Message -> Text(state.text, color = TranslationColor, fontSize = 13.sp)
                is CardState.Result -> ResultContent(state.result)
            }
        }
    }
}

@Composable
private fun LoadingContent(wordHint: String) {
    Column {
        if (wordHint.isNotBlank()) {
            Text(wordHint, color = WordColor, fontWeight = FontWeight.Bold, fontSize = 15.sp)
        }
        Text("…", color = TranslationColor, fontSize = 16.sp)
    }
}

@Composable
private fun ResultContent(r: LookupResult) {
    val englishHalf = r.meaning.isNotBlank() || r.synonyms.isNotBlank()
    val nativeHalf = r.translation.isNotBlank() || r.exampleNative.isNotBlank()

    Row(verticalAlignment = Alignment.Bottom) {
        Text(r.original, color = WordColor, fontWeight = FontWeight.Bold, fontSize = 15.sp)
        if (r.partOfSpeech.isNotBlank()) {
            Text(
                "  · ${r.partOfSpeech}",
                color = PosColor,
                fontStyle = FontStyle.Italic,
                fontSize = 11.sp,
            )
        }
    }
    if (r.meaning.isNotBlank()) {
        Text(r.meaning, color = MeaningColor, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
    }
    if (r.synonyms.isNotBlank()) {
        Text(
            r.synonyms,
            color = SynonymsColor,
            fontStyle = FontStyle.Italic,
            fontSize = 11.sp,
            modifier = Modifier.padding(top = 2.dp),
        )
    }
    if (englishHalf && nativeHalf) {
        Spacer(
            Modifier
                .padding(vertical = 6.dp)
                .fillMaxWidth()
                .height(1.dp)
                .background(DividerColor),
        )
    }
    if (r.translation.isNotBlank()) {
        Text(
            r.translation,
            color = TranslationColor,
            fontSize = 18.sp,
            modifier = Modifier.padding(top = if (englishHalf && nativeHalf) 0.dp else 4.dp),
        )
    }
    if (r.exampleNative.isNotBlank()) {
        Text(
            r.exampleNative,
            color = ExampleColor,
            fontStyle = FontStyle.Italic,
            fontSize = 13.sp,
            modifier = Modifier.padding(top = 2.dp),
        )
    }
}
