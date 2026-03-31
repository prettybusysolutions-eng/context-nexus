-- Context Nexus Schema Migration v1
-- SQLite + PostgreSQL compatible

BEGIN;

-- memories table
CREATE TABLE IF NOT EXISTS memories (
    id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    key         TEXT NOT NULL,
    value_json  TEXT NOT NULL,
    scope       TEXT NOT NULL DEFAULT 'ephemeral',  -- ephemeral | durable | pinned
    importance  INTEGER NOT NULL DEFAULT 5,           -- 1-10
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_session_id  TEXT,
    source_thread_id   TEXT,
    tags_json   TEXT NOT NULL DEFAULT '[]',
    search_text TEXT,                                 -- denormalized for keyword search
    is_pinned   INTEGER NOT NULL DEFAULT 0,
    expires_at  TIMESTAMPTZ,
    expires_in_seconds INTEGER
);

CREATE INDEX IF NOT EXISTS idx_memories_key        ON memories(key);
CREATE INDEX IF NOT EXISTS idx_memories_scope     ON memories(scope);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC);
CREATE INDEX IF NOT EXISTS idx_memories_created    ON memories(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_session   ON memories(source_session_id);
CREATE INDEX IF NOT EXISTS idx_memories_thread    ON memories(source_thread_id);
CREATE INDEX IF NOT EXISTS idx_memories_pinned    ON memories(is_pinned) WHERE is_pinned = 1;
CREATE INDEX IF NOT EXISTS idx_memories_expires   ON memories(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_memories_search    ON memories(search_text) WHERE search_text IS NOT NULL;

-- events table
CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    event_type      TEXT NOT NULL,
    session_id      TEXT,
    thread_id       TEXT,
    correlation_id  TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMPTZ,
    duration_ms     INTEGER,
    status          TEXT NOT NULL,  -- running | success | failure | error
    input_summary   TEXT,
    output_summary  TEXT,
    error_code      TEXT,
    error_message   TEXT,
    payload_json    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_session   ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_thread    ON events(thread_id);
CREATE INDEX IF NOT EXISTS idx_events_type      ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_status    ON events(status);
CREATE INDEX IF NOT EXISTS idx_events_started    ON events(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_correlation ON events(correlation_id);
CREATE INDEX IF NOT EXISTS idx_events_error      ON events(error_code) WHERE error_code IS NOT NULL;

-- run_summaries table
CREATE TABLE IF NOT EXISTS run_summaries (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    session_id      TEXT,
    thread_id       TEXT,
    goal            TEXT,
    action_summary  TEXT,
    result_summary  TEXT,
    success         INTEGER NOT NULL DEFAULT 0,
    lessons_json    TEXT NOT NULL DEFAULT '[]',
    entities_json   TEXT NOT NULL DEFAULT '[]',
    followups_json  TEXT NOT NULL DEFAULT '[]',
    score           REAL,        -- 0.0-1.0
    completion_status TEXT,
    memory_effectiveness REAL,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    error_burden    INTEGER NOT NULL DEFAULT 0,
    execution_efficiency REAL,
    suggested_optimization TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_runs_session  ON run_summaries(session_id);
CREATE INDEX IF NOT EXISTS idx_runs_thread  ON run_summaries(thread_id);
CREATE INDEX IF NOT EXISTS idx_runs_created ON run_summaries(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_success ON run_summaries(success) WHERE success = 0;

-- secrets table
CREATE TABLE IF NOT EXISTS secrets (
    id                  TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name                TEXT NOT NULL UNIQUE,
    encrypted_value     TEXT NOT NULL,
    metadata_json       TEXT NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_validated_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_secrets_name ON secrets(name);

-- checkpoints table
CREATE TABLE IF NOT EXISTS checkpoints (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    session_id      TEXT NOT NULL,
    thread_id       TEXT,
    checkpoint_type TEXT NOT NULL,  -- reset | shutdown | manual
    state_json      TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_session ON checkpoints(session_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_thread  ON checkpoints(thread_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_type    ON checkpoints(checkpoint_type);

-- token_registry table (for token lifecycle management)
CREATE TABLE IF NOT EXISTS token_registry (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    provider        TEXT NOT NULL,
    account_name    TEXT NOT NULL,
    encrypted_access_token  TEXT,
    encrypted_refresh_token TEXT,
    access_expires_at      TIMESTAMPTZ,
    refresh_expires_at      TIMESTAMPTZ,
    metadata_json   TEXT NOT NULL DEFAULT '{}',
    last_refresh_at TIMESTAMPTZ,
    last_error      TEXT,
    error_count     INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'active',  -- active | expired | error | retired
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_token_provider_account ON token_registry(provider, account_name);
CREATE INDEX IF NOT EXISTS idx_token_expires ON token_registry(access_expires_at) WHERE access_expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_token_status  ON token_registry(status);

COMMIT;
