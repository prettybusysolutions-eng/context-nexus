"""Structured logging service for Context Nexus."""
import json
import re
from typing import Optional
from storage.sqlite_adapter import SQLiteAdapter

# Patterns that look like secrets/credentials
SECRET_PATTERNS = [
    (re.compile(r'(sk_live_[a-zA-Z0-9]{20,})'), '[STRIPE_KEY]'),
    (re.compile(r'(sk_test_[a-zA-Z0-9]{20,})'), '[STRIPE_KEY]'),
    (re.compile(r'(sk-[a-zA-Z0-9]{20,})'), '[OPENAI_KEY]'),
    (re.compile(r'(ghp_[a-zA-Z0-9]{20,})'), '[GITHUB_TOKEN]'),
    (re.compile(r'(xox[baprs]-[a-zA-Z0-9]{10,})'), '[SLACK_TOKEN]'),
    (re.compile(r'(Bearer\s+[a-zA-Z0-9._-]+)'), '[BEARER_TOKEN]'),
    (re.compile(r'(refresh[_token]*["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_-]{20,})', re.I), '[REFRESH_TOKEN]'),
    (re.compile(r'("[a-zA-Z0-9_-]{40,}")'), '[TOKEN]'),
    (re.compile(r"(password[=:]\s*['\"])([^'\"]+)(['\"])", re.I), r'\1[REDACTED]\3'),
    (re.compile(r"(api[_-]?key[=:]\s*['\"])([^'\"]+)(['\"])", re.I), r'\1[REDACTED]\3'),
    (re.compile(r'(-----BEGIN [A-Z]+ PRIVATE KEY-----)', re.M), '[PRIVATE_KEY]'),
    (re.compile(r'(ak_live_[a-zA-Z0-9]{20,})'), '[STRIPE_KEY]'),
]


def redact(text: str) -> str:
    """Redact credential-like strings from text."""
    if not isinstance(text, str):
        text = str(text)
    result = text
    for pattern, replacement in SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


class LoggingService:
    """Structured event logging with redaction."""

    def __init__(self, storage: SQLiteAdapter):
        self._s = storage

    def log_start(self, event_type: str,
                  session_id: str = None,
                  thread_id: str = None,
                  correlation_id: str = None,
                  input_summary: str = None,
                  payload: dict = None) -> str:
        """Begin a structured event."""
        return self._s.event_start(
            event_type=event_type,
            session_id=session_id,
            thread_id=thread_id,
            correlation_id=correlation_id,
            input_summary=redact(input_summary) if input_summary else None,
            payload={k: redact(str(v)) for k, v in (payload or {}).items()},
        )

    def log_end(self, event_id: str,
                status: str,
                output_summary: str = None,
                error_code: str = None,
                error_message: str = None) -> bool:
        """Complete an event."""
        return self._s.event_end(
            event_id=event_id,
            status=status,
            output_summary=redact(output_summary) if output_summary else None,
            error_code=error_code,
            error_message=redact(error_message) if error_message else None,
        )

    def log_run(self, session_id: str,
                thread_id: str,
                goal: str,
                action_summary: str,
                result_summary: str,
                success: bool,
                tools_used: list = None,
                files_touched: list = None,
                error_code: str = None,
                error_message: str = None,
                duration_ms: int = None) -> str:
        """Log a complete run as event + summary."""
        event_payload = {
            'tools': tools_used or [],
            'files': files_touched or [],
        }
        event_id = self._s.event_start(
            event_type='run',
            session_id=session_id,
            thread_id=thread_id,
            input_summary=redact(goal[:200]),
            payload=event_payload,
        )

        status = 'success' if success else 'failure'
        self._s.event_end(
            event_id=event_id,
            status=status,
            output_summary=redact(result_summary[:500]) if result_summary else None,
            error_code=error_code,
            error_message=redact(error_message) if error_message else None,
        )

        run_id = self._s.run_save(
            session_id=session_id,
            thread_id=thread_id,
            goal=redact(goal[:500]),
            action_summary=redact(action_summary[:500]),
            result_summary=redact(result_summary[:500]) if result_summary else None,
            success=success,
            completion_status=status,
        )
        return run_id

    def query_failures(self, limit: int = 20) -> list:
        """Get recent failure events."""
        return self._s.event_query(limit=limit, failures_only=True)

    def query_events(self, limit: int = 50,
                     session_id: str = None,
                     event_type: str = None,
                     status: str = None) -> list:
        """Query events."""
        return self._s.event_query(
            limit=limit,
            session_id=session_id,
            event_type=event_type,
            status=status,
        )

    def summarize_session(self, session_id: str) -> dict:
        """Summarize a session."""
        events = self._s.event_query(limit=100, session_id=session_id)
        runs = self._s.run_get(limit=50, session_id=session_id)
        if not events and not runs:
            return {'session_id': session_id, 'events': 0, 'runs': 0}

        successes = sum(1 for e in events if e.get('status') == 'success')
        failures = sum(1 for e in events if e.get('status') in ('failure', 'error'))
        total_duration = sum(e.get('duration_ms', 0) for e in events if e.get('duration_ms'))
        avg_duration = total_duration / len(events) if events else 0

        return {
            'session_id': session_id,
            'total_events': len(events),
            'successes': successes,
            'failures': failures,
            'runs': len(runs),
            'total_duration_ms': total_duration,
            'avg_duration_ms': round(avg_duration, 1),
            'first_event': events[-1]['started_at'] if events else None,
            'last_event': events[0]['started_at'] if events else None,
        }
