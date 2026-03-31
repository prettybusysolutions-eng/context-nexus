"""Memory service for Context Nexus."""
import json
import hashlib
from typing import Any, Optional
from storage.sqlite_adapter import SQLiteAdapter


class MemoryService:
    """Structured memory with importance, scope, tagging, and TTL."""

    def __init__(self, storage: SQLiteAdapter):
        self._s = storage

    def set(self, key: str, value: Any, scope: str = 'durable',
            importance: int = 5, tags: list = None,
            session_id: str = None, thread_id: str = None,
            pinned: bool = False, ttl_seconds: int = None,
            source_session_id: str = None,
            source_thread_id: str = None) -> dict:
        """Store a memory."""
        # Auto-pin if importance >= 9
        if importance >= 9:
            pinned = True
        # Auto-scope: if pinned, force durable
        if pinned and scope == 'ephemeral':
            scope = 'durable'
        result = self._s.memory_set(
            key=key,
            value=value,
            scope=scope,
            importance=importance,
            tags=tags or [],
            source_session_id=source_session_id or session_id,
            source_thread_id=source_thread_id or thread_id,
            is_pinned=pinned,
            expires_in_seconds=ttl_seconds,
        )
        return result

    def get(self, key: str, scope: str = None) -> Optional[Any]:
        """Retrieve a memory by key."""
        row = self._s.memory_get(key=key, scope=scope)
        if not row:
            return None
        try:
            return json.loads(row['value_json'])
        except (json.JSONDecodeError, TypeError, KeyError):
            return row.get('value_json')

    def search(self, query: str, limit: int = 10,
               scope: str = None, session_id: str = None) -> list:
        """Search memories by keyword."""
        rows = self._s.memory_search(query=query, limit=limit,
                                   scope=scope, session_id=session_id)
        results = []
        for row in rows:
            try:
                value = json.loads(row['value_json'])
            except (json.JSONDecodeError, TypeError, KeyError):
                value = row.get('value_json', '')
            results.append({
                'id': row['id'],
                'key': row['key'],
                'value': value,
                'scope': row['scope'],
                'importance': row['importance'],
                'is_pinned': bool(row['is_pinned']),
                'created_at': row['created_at'],
                'updated_at': row['updated_at'],
                'tags': row.get('tags_json', []),
                'session_id': row.get('source_session_id'),
                'thread_id': row.get('source_thread_id'),
            })
        return results

    def recent(self, limit: int = 10, scope: str = None) -> list:
        """Get most recent memories."""
        rows = self._s.memory_recent(limit=limit, scope=scope)
        results = []
        for row in rows:
            try:
                value = json.loads(row['value_json'])
            except (json.JSONDecodeError, TypeError, KeyError):
                value = row.get('value_json', '')
            results.append({
                'key': row['key'],
                'value': value,
                'scope': row['scope'],
                'importance': row['importance'],
                'is_pinned': bool(row['is_pinned']),
                'created_at': row['created_at'],
            })
        return results

    def pin(self, key: str, pin: bool = True) -> bool:
        """Pin or unpin a memory."""
        return self._s.memory_pin(key=key, pin=pin)

    def forget(self, key: str, scope: str = None) -> bool:
        """Delete a memory."""
        return self._s.memory_forget(key=key, scope=scope)

    def compact(self, keep_durable: int = 500, keep_ephemeral: int = 50) -> int:
        """Run compaction, return number of deleted memories."""
        return self._s.memory_compact(
            keep_durable=keep_durable,
            keep_ephemeral=keep_ephemeral,
        )

    def distill(self, session_id: str, thread_id: str,
                goal: str, tools_used: list,
                files_touched: list, result: str,
                success: bool, followups: list = None,
                entities: list = None) -> str:
        """Create a distilled run summary memory."""
        return self._s.run_save(
            session_id=session_id,
            thread_id=thread_id,
            goal=goal,
            action_summary=f"tools: {', '.join(tools_used)}. files: {', '.join(files_touched)}",
            result_summary=result[:500] if result else '',
            success=success,
            followups=followups or [],
            entities=entities or [],
            memory_effectiveness=0.7,  # estimated until scored
        )
