# Context Nexus — Storage

## SQLite (Default)

### Location
- Default: `~/.openclaw/context-nexus/nexus.db`
- Configurable via `CONTEXT_NEXUS_DB_PATH`
- Set `CONTEXT_NEXUS_DB_DIR` to move entire directory

### Schema

```sql
-- memories
CREATE TABLE memories (
    id TEXT PRIMARY KEY,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'ephemeral',  -- ephemeral|durable|pinned
    importance INTEGER NOT NULL DEFAULT 5,
    tags TEXT,  -- JSON array
    source_tool TEXT,
    source_session TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT,
    is_pinned INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_memories_key ON memories(key);
CREATE INDEX idx_memories_scope ON memories(scope);
CREATE INDEX idx_memories_importance ON memories(importance DESC);
CREATE INDEX idx_memories_updated ON memories(updated_at DESC);

-- events
CREATE TABLE events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,  -- tool_call|run|error|checkpoint|auth_failure
    session_id TEXT,
    thread_id TEXT,
    correlation_id TEXT,
    payload TEXT,  -- JSON
    error_type TEXT,
    error_message TEXT,
    redacted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_events_session ON events(session_id);
CREATE INDEX idx_events_type ON events(event_type);
CREATE INDEX idx_events_created ON events(created_at DESC);

-- run_summaries
CREATE TABLE run_summaries (
    id TEXT PRIMARY KEY,
    session_id TEXT UNIQUE NOT NULL,
    thread_id TEXT,
    goal TEXT,
    action_summary TEXT,
    result_summary TEXT,
    score REAL,
    success INTEGER,
    retry_count INTEGER DEFAULT 0,
    error_burden INTEGER DEFAULT 0,
    tools_used TEXT,  -- JSON array
    files_touched TEXT,  -- JSON array
    errors TEXT,  -- JSON array
    created_at TEXT NOT NULL
);

-- secrets
CREATE TABLE secrets (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    ciphertext TEXT NOT NULL,
    metadata TEXT,  -- JSON object
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_secrets_name ON secrets(name);

-- checkpoints
CREATE TABLE checkpoints (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    thread_id TEXT,
    snapshot TEXT NOT NULL,  -- JSON
    created_at TEXT NOT NULL
);
CREATE INDEX idx_checkpoints_session ON checkpoints(session_id);

-- token_registry
CREATE TABLE token_registry (
    provider TEXT PRIMARY KEY,
    access_token TEXT,
    refresh_token TEXT,
    expires_at TEXT,
    scope TEXT,
    metadata TEXT,  -- JSON
    updated_at TEXT NOT NULL
);
```

### WAL Mode
SQLite uses WAL (Write-Ahead Logging) for:
- Concurrent reads during writes
- Crash resilience
- No locking on read-heavy workloads

### Backup
```bash
cp ~/.openclaw/context-nexus/nexus.db ~/.openclaw/context-nexus/nexus.db.backup
```

---

## PostgreSQL (Future)

### Connection
Set `DATABASE_URL` environment variable:
```
DATABASE_URL=postgresql://user:pass@host:5432/nexus
```

### Adapter Swap
Same schema, different transport. Code path:
```python
if DATABASE_URL:
    adapter = PostgresAdapter(DATABASE_URL)
else:
    adapter = SQLiteAdapter()
```

### Known Differences
- PostgreSQL: network latency on every query
- SQLite: zero-latency local I/O
- PostgreSQL: shared across multiple agents
- SQLite: single-agent local only

---

## Compaction

### Policy by Scope
| Scope | Max Records | Delete Rule |
|-------|-------------|-------------|
| ephemeral | 50 | Keep top 50 by importance |
| durable | 500 | Keep top 500 by importance |
| pinned | unlimited | Never deleted |

### Trigger
- Automatic: every 100 `after_tool_call` events
- Manual: `nexus_admin action=compact`

### Process
```python
def compact():
    for scope in ['ephemeral', 'durable']:
        limit = 50 if scope == 'ephemeral' else 500
        with get_db() as db:
            db.execute("""
                DELETE FROM memories
                WHERE scope = ? AND id NOT IN (
                    SELECT id FROM memories
                    WHERE scope = ?
                    ORDER BY importance DESC
                    LIMIT ?
                )
            """, [scope, scope, limit])
```

---

## Export / Import

### Export
```bash
nexus_admin action=export_snapshot
# Returns JSON: {"memories": [...], "events": [...], ...}
```

### Import
```python
nexus_admin action=import_snapshot data='{"memories": [...], ...}'
```

### Scoped Export
```python
nexus_admin action=export_snapshot scope=durable
```
