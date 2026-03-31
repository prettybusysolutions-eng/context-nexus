# Context Nexus — Lifecycle

## Session Lifecycle

### Session Start
1. OpenClaw session begins
2. Plugin `index.js` loads → starts `nexus_service.py` subprocess
3. `before_prompt_build` hook fires
4. Recent durable memories retrieved and injected into context
5. Session is now memory-aware from turn 1

### During Session
- Every tool call triggers `after_tool_call` hook
- Events logged asynchronously (non-blocking)
- Significant tool calls auto-flagged for distillation
- Secrets never logged — redacted automatically

### Session End
1. `session_end` hook fires
2. Deterministic distillation runs (no model call)
3. Run summary written to `run_summaries` table
4. Memory compaction runs if threshold reached
5. Subprocess exits cleanly

### On Error
1. `on_error` hook fires immediately
2. Error classified into 8 types
3. Failure event logged with full context
4. If auth error: token registry updated
5. Error summary created for replay

---

## Memory Lifecycle

### Memory Creation
- `memory_set` → write to `memories` table with scope, importance, TTL
- Importance 9-10 → auto-pinned
- Ephemeral: TTL = session end
- Durable: TTL = 90 days default
- Pinned: TTL = never

### Memory Retrieval
- `memory_get` → exact key match, scope filter
- `memory_search` → FTS on key, value, tags
- `memory_recent` → ordered by `updated_at` desc, scope filter

### Memory Deletion
- `memory_forget` → hard delete by key
- Compaction → delete by importance + scope rules
- `wipe` → truncate all tables

### Compaction Triggers
- Every 100th `after_tool_call` event
- Manual trigger via `nexus_admin action=compact`
- On `session_end` if ephemeral count > 50

---

## Secrets Lifecycle

### Storage
- `secret_store` → encrypt value with PBKDF2 key → store ciphertext
- Metadata stored separately (name, type, updated_at)
- Values never logged, never in error messages

### Retrieval
- `secret_get` → decrypt on-demand
- Fail-closed: any decryption error → empty response
- No caching of decrypted values in memory

### Rotation
- `secret_delete` + `secret_store` = rotation
- Old secret name can be reused after deletion
- Token registry tracks which credentials are active

---

## Run Distillation Lifecycle

### Trigger Points
- `session_end` hook (automatic)
- `nexus_replay action=distill_run` (manual)

### Process
1. Fetch all events for session
2. Extract tool names, file paths, URLs, error codes via regex
3. Compose deterministic `action_summary` and `result_summary`
4. Score run: success × 0.5 + efficiency × 0.25 + memory × 0.25
5. Store in `run_summaries`

### Replay
- `explain_failure` → query failure events → classify → suggest recovery
- `compare_runs` → side-by-side score and pattern analysis

---

## Schema Migration Lifecycle

### Version Tracking
- `schema_version` table tracks current version
- Migrations are forward-only
- Each migration is idempotent

### Migration Process
1. Check current version in DB
2. Apply unapplied migrations in order
3. Update version atomically
4. On failure: rollback transaction, exit with error

### Compatibility
- SQLite schema is PostgreSQL-compatible
- Network PostgreSQL adapter future: same schema, network transport

---

## Plugin Lifecycle

### Install
1. Copy plugin files to `~/.openclaw/plugins/context-nexus/`
2. Add entry to `~/.openclaw/openclaw.json`
3. Run `./scripts/install` to bootstrap storage
4. Restart OpenClaw gateway

### Enable/Disable
- Enabled: add to `plugins.entries` with `enabled: true`
- Disabled: remove entry or set `enabled: false`
- No restart required for config-only changes

### Uninstall
1. Remove plugin entry from `openclaw.json`
2. Remove plugin directory
3. Database retained unless `wipe` explicitly called
