"""SQLite storage adapter for Context Nexus."""
import sqlite3
import json
import os
import threading
from contextlib import contextmanager
from typing import Any, Generator, Optional
from datetime import datetime, timezone

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'ephemeral',
    importance INTEGER NOT NULL DEFAULT 5,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    source_session_id TEXT,
    source_thread_id TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
    search_text TEXT,
    is_pinned INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT,
    expires_in_seconds INTEGER
);
CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key);
CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_session ON memories(source_session_id);
CREATE INDEX IF NOT EXISTS idx_memories_thread ON memories(source_thread_id);
CREATE INDEX IF NOT EXISTS idx_memories_pinned ON memories(is_pinned) WHERE is_pinned=1;

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    session_id TEXT,
    thread_id TEXT,
    correlation_id TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration_ms INTEGER,
    status TEXT NOT NULL,
    input_summary TEXT,
    output_summary TEXT,
    error_code TEXT,
    error_message TEXT,
    payload_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_thread ON events(thread_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
CREATE INDEX IF NOT EXISTS idx_events_started ON events(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_error ON events(error_code) WHERE error_code IS NOT NULL;

CREATE TABLE IF NOT EXISTS run_summaries (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    thread_id TEXT,
    goal TEXT,
    action_summary TEXT,
    result_summary TEXT,
    success INTEGER NOT NULL DEFAULT 0,
    lessons_json TEXT NOT NULL DEFAULT '[]',
    entities_json TEXT NOT NULL DEFAULT '[]',
    followups_json TEXT NOT NULL DEFAULT '[]',
    score REAL,
    completion_status TEXT,
    memory_effectiveness REAL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    error_burden INTEGER NOT NULL DEFAULT 0,
    execution_efficiency REAL,
    suggested_optimization TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_session ON run_summaries(session_id);
CREATE INDEX IF NOT EXISTS idx_runs_created ON run_summaries(created_at DESC);

CREATE TABLE IF NOT EXISTS secrets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    encrypted_value TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_validated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_secrets_name ON secrets(name);

CREATE TABLE IF NOT EXISTS checkpoints (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    thread_id TEXT,
    checkpoint_type TEXT NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_checkpoints_session ON checkpoints(session_id);

CREATE TABLE IF NOT EXISTS token_registry (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    account_name TEXT NOT NULL,
    encrypted_access_token TEXT,
    encrypted_refresh_token TEXT,
    access_expires_at TEXT,
    refresh_expires_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    last_refresh_at TEXT,
    last_error TEXT,
    error_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_token_provider_account ON token_registry(provider, account_name);
CREATE INDEX IF NOT EXISTS idx_token_expires ON token_registry(access_expires_at) WHERE access_expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_token_status ON token_registry(status);
"""


class SQLiteAdapter:
    """Thread-safe SQLite adapter with automatic schema init."""

    def __init__(self, db_path: str = None):
        if db_path is None:
            base = os.environ.get('CONTEXT_NEXUS_DB_DIR', os.path.expanduser('~/.openclaw/context-nexus'))
            os.makedirs(base, exist_ok=True)
            db_path = os.path.join(base, 'nexus.db')
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        """Get thread-local connection."""
        conn = getattr(self._local, 'conn', None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for transactions."""
        conn = self._conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_db(self):
        """Initialize schema."""
        with self.transaction() as conn:
            conn.executescript(SCHEMA_SQL)

    def now_iso(self) -> str:
        """Return current UTC time as ISO string."""
        return datetime.now(timezone.utc).isoformat()

    def now_ts(self) -> str:
        """Return current UTC time as TEXT for SQLite."""
        return self.now_iso()

    # ── Memory CRUD ────────────────────────────────────────────────────────────

    def memory_set(self, key: str, value: Any, scope: str = 'durable',
                   importance: int = 5, tags: list = None,
                   source_session_id: str = None, source_thread_id: str = None,
                   is_pinned: bool = False, expires_in_seconds: int = None) -> dict:
        """Insert or update a memory record."""
        import uuid
        now = self.now_iso()
        id_ = str(uuid.uuid4())
        value_json = json.dumps(value)
        tags_json = json.dumps(tags or [])
        search_text = f"{key} {json.dumps(value)}"[:1000]
        expires_at = None
        if expires_in_seconds:
            from datetime import timedelta
            exp = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
            expires_at = exp.isoformat()

        with self.transaction() as conn:
            # Upsert on key + scope
            cur = conn.execute("""
                SELECT id FROM memories WHERE key = ? AND scope = ?
            """, (key, scope))
            existing = cur.fetchone()

            if existing:
                conn.execute("""
                    UPDATE memories SET
                        value_json=?, importance=?, updated_at=?,
                        tags_json=?, search_text=?, is_pinned=?,
                        expires_at=?, expires_in_seconds=?,
                        source_session_id=COALESCE(?, source_session_id),
                        source_thread_id=COALESCE(?, source_thread_id)
                    WHERE key=? AND scope=?
                """, (value_json, importance, now, tags_json, search_text,
                      int(is_pinned), expires_at, expires_in_seconds,
                      source_session_id, source_thread_id, key, scope))
            else:
                conn.execute("""
                    INSERT INTO memories (id, key, value_json, scope, importance,
                        created_at, updated_at, source_session_id, source_thread_id,
                        tags_json, search_text, is_pinned, expires_at, expires_in_seconds)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (id_, key, value_json, scope, importance, now, now,
                      source_session_id, source_thread_id, tags_json, search_text,
                      int(is_pinned), expires_at, expires_in_seconds))
        return {"id": id_, "key": key, "scope": scope, "importance": importance}

    def memory_get(self, key: str, scope: str = None) -> Optional[dict]:
        """Retrieve memory by key and optional scope."""
        conn = self._conn()
        if scope:
            row = conn.execute("""
                SELECT * FROM memories
                WHERE key=? AND scope=? AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY importance DESC, created_at DESC LIMIT 1
            """, (key, scope, self.now_iso())).fetchone()
        else:
            row = conn.execute("""
                SELECT * FROM memories
                WHERE key=? AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY importance DESC, created_at DESC LIMIT 1
            """, (key, self.now_iso())).fetchone()

        if not row:
            return None
        return self._row_to_dict(row)

    def memory_search(self, query: str, limit: int = 10,
                     scope: str = None, session_id: str = None) -> list:
        """Keyword + metadata search."""
        conn = self._conn()
        q = f"%{query}%"
        if scope:
            rows = conn.execute("""
                SELECT * FROM memories
                WHERE (search_text LIKE ? OR key LIKE ?)
                  AND scope=? AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY importance DESC, created_at DESC LIMIT ?
            """, (q, q, scope, self.now_iso(), limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM memories
                WHERE (search_text LIKE ? OR key LIKE ?)
                  AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY importance DESC, created_at DESC LIMIT ?
            """, (q, q, self.now_iso(), limit)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def memory_recent(self, limit: int = 10, scope: str = None) -> list:
        """Get most recent memories."""
        conn = self._conn()
        if scope:
            rows = conn.execute("""
                SELECT * FROM memories
                WHERE scope=? AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY created_at DESC LIMIT ?
            """, (scope, self.now_iso(), limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM memories
                WHERE (expires_at IS NULL OR expires_at > ?)
                ORDER BY created_at DESC LIMIT ?
            """, (self.now_iso(), limit)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def memory_pin(self, key: str, pin: bool = True) -> bool:
        """Pin or unpin a memory."""
        with self.transaction() as conn:
            n = conn.execute("""
                UPDATE memories SET is_pinned=? WHERE key=?
            """, (int(pin), key)).rowcount
        return n > 0

    def memory_forget(self, key: str, scope: str = None) -> bool:
        """Delete memory by key."""
        with self.transaction() as conn:
            if scope:
                n = conn.execute("DELETE FROM memories WHERE key=? AND scope=?",
                                 (key, scope)).rowcount
            else:
                n = conn.execute("DELETE FROM memories WHERE key=?",
                                 (key,)).rowcount
        return n > 0

    def memory_compact(self, keep_durable: int = 500, keep_ephemeral: int = 50) -> int:
        """Remove low-importance old memories, keep important/pinned ones."""
        with self.transaction() as conn:
            # ephemeral: remove old/low importance beyond keep_ephemeral
            cur = conn.execute("""
                SELECT id FROM memories
                WHERE scope='ephemeral' AND is_pinned=0
                ORDER BY importance ASC, created_at ASC
            """)
            all_ids = [r[0] for r in cur.fetchall()]
            delete_ids = all_ids[keep_ephemeral:]
            deleted = 0
            if delete_ids:
                placeholders = ','.join('?' * len(delete_ids))
                deleted = conn.execute(f"""
                    DELETE FROM memories WHERE id IN ({placeholders})
                """, delete_ids).rowcount

            # durable: keep top keep_durable by importance
            cur = conn.execute("""
                SELECT id FROM memories
                WHERE scope='durable' AND is_pinned=0
                ORDER BY importance DESC, created_at DESC
            """)
            durable_ids = [r[0] for r in cur.fetchall()]
            delete_durable = durable_ids[keep_durable:]
            if delete_durable:
                placeholders = ','.join('?' * len(delete_durable))
                deleted += conn.execute(f"""
                    DELETE FROM memories WHERE id IN ({placeholders})
                """, delete_durable).rowcount
        return deleted

    # ── Event logging ──────────────────────────────────────────────────────────

    def event_start(self, event_type: str, session_id: str = None,
                    thread_id: str = None, correlation_id: str = None,
                    input_summary: str = None, payload: dict = None) -> str:
        """Start an event, return event id."""
        import uuid
        id_ = str(uuid.uuid4())
        now = self.now_iso()
        with self.transaction() as conn:
            conn.execute("""
                INSERT INTO events (id, event_type, session_id, thread_id,
                    correlation_id, started_at, status, input_summary, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?, ?)
            """, (id_, event_type, session_id, thread_id, correlation_id,
                  now, input_summary, json.dumps(payload or {}), now))
        return id_

    def event_end(self, event_id: str, status: str, output_summary: str = None,
                  error_code: str = None, error_message: str = None) -> bool:
        """End an event with result."""
        now = self.now_iso()
        with self.transaction() as conn:
            row = conn.execute("SELECT started_at FROM events WHERE id=?",
                              (event_id,)).fetchone()
            if not row:
                return False
            started = datetime.fromisoformat(row[0].replace('Z', '+00:00'))
            ended = datetime.now(timezone.utc)
            duration_ms = int((ended - started).total_seconds() * 1000)
            conn.execute("""
                UPDATE events SET
                    ended_at=?, duration_ms=?, status=?,
                    output_summary=?, error_code=?, error_message=?
                WHERE id=?
            """, (now, duration_ms, status, output_summary,
                  error_code, error_message, event_id))
        return True

    def event_query(self, limit: int = 50, status: str = None,
                    session_id: str = None, event_type: str = None,
                    failures_only: bool = False) -> list:
        """Query events."""
        conn = self._conn()
        conditions = []
        params = []
        if status:
            conditions.append("status=?")
            params.append(status)
        if session_id:
            conditions.append("session_id=?")
            params.append(session_id)
        if event_type:
            conditions.append("event_type=?")
            params.append(event_type)
        if failures_only:
            conditions.append("status IN ('failure','error')")
        where = " AND ".join(conditions) if conditions else "1=1"
        rows = conn.execute(f"""
            SELECT * FROM events
            WHERE {where}
            ORDER BY started_at DESC LIMIT ?
        """, params + [limit]).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ── Run summaries ──────────────────────────────────────────────────────────

    def run_save(self, session_id: str = None, thread_id: str = None,
                 goal: str = None, action_summary: str = None,
                 result_summary: str = None, success: bool = True,
                 score: float = None, completion_status: str = None,
                 retry_count: int = 0, error_burden: int = 0,
                 execution_efficiency: float = None,
                 memory_effectiveness: float = None,
                 lessons: list = None, entities: list = None,
                 followups: list = None,
                 suggested_optimization: str = None) -> str:
        """Save a run summary."""
        import uuid
        id_ = str(uuid.uuid4())
        now = self.now_iso()
        with self.transaction() as conn:
            conn.execute("""
                INSERT INTO run_summaries (id, session_id, thread_id, goal, action_summary,
                    result_summary, success, score, completion_status,
                    memory_effectiveness, retry_count, error_burden,
                    execution_efficiency, lessons_json, entities_json,
                    followups_json, suggested_optimization, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (id_, session_id, thread_id, goal, action_summary, result_summary,
                  int(success), score, completion_status,
                  memory_effectiveness, retry_count, error_burden,
                  execution_efficiency,
                  json.dumps(lessons or []),
                  json.dumps(entities or []),
                  json.dumps(followups or []),
                  suggested_optimization, now))
        return id_

    def run_get(self, limit: int = 10, session_id: str = None) -> list:
        """Get run summaries."""
        conn = self._conn()
        if session_id:
            rows = conn.execute("""
                SELECT * FROM run_summaries
                WHERE session_id=?
                ORDER BY created_at DESC LIMIT ?
            """, (session_id, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM run_summaries ORDER BY created_at DESC LIMIT ?
            """, (limit,)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def run_score(self, run_id: str) -> dict:
        """Compute a run score from stored metrics."""
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM run_summaries WHERE id=?", (run_id,)).fetchone()
        if not row:
            return {}
        r = self._row_to_dict(row)
        # Weighted composite: success=50%, efficiency=25%, memory=25%
        base = 1.0 if r['success'] else 0.0
        eff = float(r.get('execution_efficiency') or 0.5)
        mem = float(r.get('memory_effectiveness') or 0.5)
        score = base * 0.5 + eff * 0.25 + mem * 0.25
        suggestions = []
        if not r['success']:
            suggestions.append("Investigate failure cause in event log")
        if r.get('retry_count', 0) > 3:
            suggestions.append("High retry count — check error classification")
        if r.get('error_burden', 0) > 5:
            suggestions.append("High error burden — review error patterns")
        return {
            "run_id": run_id,
            "composite_score": round(score, 3),
            "components": {
                "success": base,
                "efficiency": eff,
                "memory": mem
            },
            "suggestions": suggestions
        }

    # ── Checkpoints ───────────────────────────────────────────────────────────

    def checkpoint_save(self, session_id: str, thread_id: str = None,
                       checkpoint_type: str = 'reset', state: dict = None) -> str:
        """Save a session checkpoint."""
        import uuid
        id_ = str(uuid.uuid4())
        now = self.now_iso()
        with self.transaction() as conn:
            conn.execute("""
                INSERT INTO checkpoints (id, session_id, thread_id, checkpoint_type, state_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (id_, session_id, thread_id, checkpoint_type, json.dumps(state or {}), now))
        return id_

    def checkpoint_list(self, session_id: str = None, limit: int = 20) -> list:
        """List checkpoints."""
        conn = self._conn()
        if session_id:
            rows = conn.execute("""
                SELECT * FROM checkpoints
                WHERE session_id=?
                ORDER BY created_at DESC LIMIT ?
            """, (session_id, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM checkpoints ORDER BY created_at DESC LIMIT ?
            """, (limit,)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ── Token registry ────────────────────────────────────────────────────────

    def token_set(self, provider: str, account_name: str,
                  access_token: str = None, refresh_token: str = None,
                  access_expires_at: str = None,
                  refresh_expires_at: str = None,
                  metadata: dict = None) -> bool:
        """Store or update token credentials."""
        with self.transaction() as conn:
            existing = conn.execute("""
                SELECT id FROM token_registry WHERE provider=? AND account_name=?
            """, (provider, account_name)).fetchone()
            now = self.now_iso()
            if existing:
                conn.execute("""
                    UPDATE token_registry SET
                        encrypted_access_token=?, encrypted_refresh_token=?,
                        access_expires_at=?, refresh_expires_at=?,
                        metadata_json=?, updated_at=?,
                        last_refresh_at=CASE WHEN access_token IS NOT NULL THEN ? ELSE last_refresh_at END
                    WHERE provider=? AND account_name=?
                """, (access_token, refresh_token, access_expires_at, refresh_expires_at,
                      json.dumps(metadata or {}), now, now, provider, account_name))
            else:
                conn.execute("""
                    INSERT INTO token_registry (provider, account_name, encrypted_access_token,
                        encrypted_refresh_token, access_expires_at, refresh_expires_at,
                        metadata_json, created_at, updated_at, last_refresh_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (provider, account_name, access_token, refresh_token,
                      access_expires_at, refresh_expires_at,
                      json.dumps(metadata or {}), now, now, now))
        return True

    def token_get(self, provider: str, account_name: str) -> Optional[dict]:
        """Get token credentials."""
        conn = self._conn()
        row = conn.execute("""
            SELECT * FROM token_registry WHERE provider=? AND account_name=?
        """, (provider, account_name)).fetchone()
        return self._row_to_dict(row) if row else None

    def token_record_error(self, provider: str, account_name: str,
                           error: str) -> bool:
        """Record a token auth error."""
        with self.transaction() as conn:
            n = conn.execute("""
                UPDATE token_registry SET
                    error_count=error_count+1,
                    last_error=?,
                    updated_at=?
                WHERE provider=? AND account_name=?
            """, (error, self.now_iso(), provider, account_name)).rowcount
        return n > 0

    def token_mark_expired(self, provider: str, account_name: str) -> bool:
        """Mark token as expired."""
        with self.transaction() as conn:
            n = conn.execute("""
                UPDATE token_registry SET status='expired', updated_at=?,
                    last_error='Token marked expired by lifecycle check'
                WHERE provider=? AND account_name=?
            """, (self.now_iso(), provider, account_name)).rowcount
        return n > 0

    def token_is_expired(self, provider: str, account_name: str) -> bool:
        """Check if access token is expired or near expiry."""
        conn = self._conn()
        row = conn.execute("""
            SELECT access_expires_at FROM token_registry
            WHERE provider=? AND account_name=? AND status='active'
        """, (provider, account_name)).fetchone()
        if not row or not row['access_expires_at']:
            return True
        exp = datetime.fromisoformat(row['access_expires_at'].replace('Z', '+00:00'))
        # Consider expired if < 60 seconds remaining
        return (exp - datetime.now(timezone.utc)).total_seconds() < 60

    # ── Secrets ───────────────────────────────────────────────────────────────

    def secret_store(self, name: str, encrypted_value: str,
                     metadata: dict = None) -> bool:
        """Store an encrypted secret."""
        now = self.now_iso()
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT id FROM secrets WHERE name=?", (name,)).fetchone()
            if existing:
                conn.execute("""
                    UPDATE secrets SET encrypted_value=?, metadata_json=?,
                        updated_at=? WHERE name=?
                """, (encrypted_value, json.dumps(metadata or {}), now, name))
            else:
                conn.execute("""
                    INSERT INTO secrets (name, encrypted_value, metadata_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (name, encrypted_value, json.dumps(metadata or {}), now, now))
        return True

    def secret_get(self, name: str) -> Optional[dict]:
        """Get a secret record (value still encrypted)."""
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM secrets WHERE name=?", (name,)).fetchone()
        return self._row_to_dict(row) if row else None

    def secret_delete(self, name: str) -> bool:
        """Delete a secret."""
        with self.transaction() as conn:
            n = conn.execute("DELETE FROM secrets WHERE name=?", (name,)).rowcount
        return n > 0

    def secret_list_names(self) -> list:
        """List secret names only (never values)."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT name, metadata_json, updated_at FROM secrets ORDER BY name").fetchall()
        return [{'name': r['name'], 'updated_at': r['updated_at'],
                 'metadata': json.loads(r['metadata_json'])} for r in rows]

    # ── Storage ops ───────────────────────────────────────────────────────────

    def storage_status(self) -> dict:
        """Return storage statistics."""
        conn = self._conn()
        cur = conn.execute
        return {
            "db_path": self.db_path,
            "db_size_bytes": os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0,
            "memories": conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0],
            "events": conn.execute("SELECT COUNT(*) FROM events").fetchone()[0],
            "run_summaries": conn.execute("SELECT COUNT(*) FROM run_summaries").fetchone()[0],
            "secrets": conn.execute("SELECT COUNT(*) FROM secrets").fetchone()[0],
            "checkpoints": conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0],
            "tokens": conn.execute("SELECT COUNT(*) FROM token_registry").fetchone()[0],
        }

    def export_snapshot(self) -> dict:
        """Export full snapshot for backup."""
        conn = self._conn()
        return {
            "memories": [self._row_to_dict(r) for r in conn.execute("SELECT * FROM memories ORDER BY created_at DESC").fetchall()],
            "events": [self._row_to_dict(r) for r in conn.execute("SELECT * FROM events ORDER BY started_at DESC").fetchall()],
            "run_summaries": [self._row_to_dict(r) for r in conn.execute("SELECT * FROM run_summaries ORDER BY created_at DESC").fetchall()],
            "exported_at": self.now_iso(),
        }

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        """Convert sqlite3.Row to dict."""
        d = dict(row)
        for k, v in d.items():
            if isinstance(v, str):
                if k.endswith('_json') or k in ('payload_json', 'lessons_json',
                                                  'entities_json', 'followups_json',
                                                  'metadata_json', 'state_json',
                                                  'tags_json'):
                    try:
                        d[k] = json.loads(v)
                    except (json.JSONDecodeError, TypeError):
                        pass
        return d
