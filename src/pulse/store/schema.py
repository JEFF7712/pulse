import aiosqlite


async def bootstrap_schema(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            source TEXT NOT NULL,
            event_type TEXT NOT NULL,
            data TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS connector_sync_state (
            source TEXT PRIMARY KEY,
            cursor TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS corrections (
            id TEXT PRIMARY KEY,
            context_id TEXT NOT NULL,
            message_text TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    # Analytics tables
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_source_stats (
            date       TEXT NOT NULL,
            source     TEXT NOT NULL,
            event_type TEXT NOT NULL,
            count      INTEGER NOT NULL,
            first_at   TEXT,
            last_at    TEXT,
            PRIMARY KEY (date, source, event_type)
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS time_blocks (
            date       TEXT NOT NULL,
            block      INTEGER NOT NULL,
            source     TEXT NOT NULL,
            count      INTEGER NOT NULL,
            PRIMARY KEY (date, block, source)
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS weekly_baselines (
            week_start TEXT NOT NULL,
            source     TEXT NOT NULL,
            event_type TEXT NOT NULL,
            avg_daily  REAL NOT NULL,
            total      INTEGER NOT NULL,
            PRIMARY KEY (week_start, source, event_type)
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS insights (
            id          TEXT PRIMARY KEY,
            title       TEXT NOT NULL,
            status      TEXT NOT NULL,
            confidence  TEXT NOT NULL,
            first_seen  TEXT NOT NULL,
            last_seen   TEXT NOT NULL,
            vault_path  TEXT NOT NULL,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Indexes on events table
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_source ON events(source)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)"
    )

    await db.commit()
