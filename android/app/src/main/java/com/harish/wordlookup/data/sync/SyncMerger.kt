package com.harish.wordlookup.data.sync

/**
 * Pure merge function — no I/O, no Android deps, so it's trivially unit
 * testable and easy to keep in lockstep with the Python mirror in
 * `kannada_lookup/sync.py`'s `merge_entries`.
 *
 * Union of both lists by `(language, key)`. Per key, keeps the entry that
 * wins under a single total order: higher `updatedAt`, then a tombstone
 * (`deleted=true`) over a live row, then a deterministic string tie-break
 * so the result never depends on argument order. Because this is exactly
 * "take the max under a total order," the result is automatically:
 *   - commutative:  merge(a, b) == merge(b, a)
 *   - idempotent:   merge(x, x) == x
 *   - associative:  merge(merge(a, b), c) == merge(a, merge(b, c))
 * which is what makes it safe to run independently on both devices and
 * always converge, regardless of who syncs first.
 */
object SyncMerger {

    private val winner = compareBy<SyncEntry> { it.updatedAt }
        .thenBy { if (it.deleted) 1 else 0 }
        .thenBy { entryTiebreakKey(it) }

    fun merge(local: List<SyncEntry>, remote: List<SyncEntry>): List<SyncEntry> =
        (local + remote)
            .groupBy { it.language to it.key }
            .values
            .map { group -> group.maxWith(winner) }

    private fun entryTiebreakKey(e: SyncEntry): String =
        "${e.original}|${e.translation}|${e.meaning}|${e.synonyms}|${e.exampleEn}|${e.exampleNative}"
}
