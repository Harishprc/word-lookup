package com.harish.wordlookup.data.cache

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface LookupDao {
    @Query(
        "SELECT * FROM lookups WHERE language = :language AND key = :key AND deleted = 0 LIMIT 1"
    )
    suspend fun get(language: String, key: String): LookupEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: LookupEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertAll(entities: List<LookupEntity>)

    /** Newest first, tombstones hidden — feeds the register screen. */
    @Query("SELECT * FROM lookups WHERE deleted = 0 ORDER BY createdAt DESC")
    fun observeAll(): Flow<List<LookupEntity>>

    /** Every row including tombstones — the sync payload needs deletions
     * represented, not silently dropped. */
    @Query("SELECT * FROM lookups")
    suspend fun allIncludingDeleted(): List<LookupEntity>

    /** Soft-delete: keeps the row as a tombstone so a later sync doesn't
     * resurrect it from the other device's older copy. */
    @Query(
        "UPDATE lookups SET deleted = 1, updatedAt = :updatedAt " +
            "WHERE language = :language AND key = :key"
    )
    suspend fun softDelete(language: String, key: String, updatedAt: Long)
}
