package com.harish.wordlookup.data.cache

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

// exportSchema = false: exporting requires a configured room.schemaLocation
// dir, and Room warns on every build without one. Nothing here consumes
// exported schemas — migrations are hand-written, and v1 is the first
// version this app has ever shipped.
@Database(entities = [LookupEntity::class], version = 1, exportSchema = false)
abstract class LookupDatabase : RoomDatabase() {
    abstract fun lookupDao(): LookupDao

    companion object {
        @Volatile private var instance: LookupDatabase? = null

        fun get(context: Context): LookupDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    LookupDatabase::class.java,
                    "lookups.db", // same file name as store.py's DB_PATH, different device
                ).build().also { instance = it }
            }
    }
}
