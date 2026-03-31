"""Distillation service — deterministic run summarization for Context Nexus."""
import json
import re
from datetime import datetime, timezone
from typing import Any


class DistillService:
    """Deterministic run distillation. Safe: never blocks on model calls."""

    TOOL_PATTERNS = [
        (re.compile(r'\bread\b'), 'read'),
        (re.compile(r'\bwrite\b'), 'write'),
        (re.compile(r'\bedit\b'), 'edit'),
        (re.compile(r'\bexec\b'), 'exec'),
        (re.compile(r'\bsearch\b'), 'search'),
        (re.compile(r'\bmemory\b'), 'memory'),
        (re.compile(r'\bcommit\b'), 'git'),
        (re.compile(r'\bdeploy\b'), 'deploy'),
        (re.compile(r'\bupload\b'), 'upload'),
        (re.compile(r'\bsend\b'), 'send'),
    ]

    def distill(self, goal: str, input_summary: str,
                raw_output: str, status: str,
                error_code: str = None,
                error_message: str = None,
                tools_used: list = None,
                token_budget: int = 500,
                timeout_seconds: float = 2.0) -> dict:
        """
        Distill a run into a structured summary.

        Always uses deterministic extraction first. Model-assisted compression
        is optional and guarded with budget + timeout.

        Returns: {goal, action_summary, result_summary, success, lessons, entities, followups}
        """
        # Deterministic extraction
        tools = tools_used or self._extract_tools(input_summary + ' ' + (raw_output or ''))
        result_snippet = (raw_output or '')[:300] if raw_output else ''
        success = status in ('success', 'ok', 'completed')

        # Extract entities (file names, URLs, service names)
        entities = self._extract_entities(input_summary + ' ' + result_snippet)

        # Extract lessons
        lessons = []
        if error_code:
            lessons.append(f"Error {error_code}: {error_message[:100] if error_message else 'unknown'}")
        if not success:
            lessons.append("Task did not complete successfully — follow-up required")

        # Extract follow-ups
        followups = self._extract_followups(raw_output or '', error_code)

        # Action summary
        action_parts = []
        if tools:
            action_parts.append(f"Used: {', '.join(tools[:5])}")
        if input_summary:
            action_parts.append(f"Input: {input_summary[:100]}")
        action_summary = ' | '.join(action_parts) if action_parts else 'No significant action'

        result_summary = result_snippet.split('\n')[-1][:200] if result_snippet else \
            ('Failed: ' + error_message[:150] if error_message else status)

        return {
            'goal': goal[:500] if goal else '',
            'action_summary': action_summary[:500],
            'result_summary': result_summary[:500],
            'success': success,
            'lessons': lessons[:5],
            'entities': entities[:10],
            'followups': followups[:5],
            'tools_used': tools[:10],
            'distilled_at': datetime.now(timezone.utc).isoformat(),
            'distillation_method': 'deterministic',
        }

    def _extract_tools(self, text: str) -> list:
        """Extract tool names from text."""
        found = set()
        lower = text.lower()
        for pattern, name in self.TOOL_PATTERNS:
            if pattern.search(lower):
                found.add(name)
        return sorted(found)

    def _extract_entities(self, text: str) -> list:
        """Extract file paths, URLs, and service identifiers."""
        entities = []
        # File paths
        for match in re.findall(r'/[\w./_-]+\.\w{1,10}', text):
            if '/tmp/' not in match and '/proc/' not in match:
                entities.append({'type': 'file', 'value': match})
        # URLs
        for match in re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', text):
            entities.append({'type': 'url', 'value': match[:200]})
        # Env vars
        for match in re.findall(r'\$([A-Z_][A-Z0-9_]{2,})', text):
            entities.append({'type': 'env_var', 'value': match})
        return entities[:10]

    def _extract_followups(self, text: str, error_code: str = None) -> list:
        """Extract next steps or unresolved items."""
        followups = []
        for pattern in [
            r'next step[:\s]+([^\n]{10,100})',
            r'todo[:\s]+([^\n]{10,100})',
            r'follow[- ]up[:\s]+([^\n]{10,100})',
            r'unresolved[:\s]+([^\n]{10,100})',
        ]:
            for match in re.finditer(pattern, text, re.I):
                followups.append(match.group(1).strip())
        if error_code and not followups:
            followups.append(f'Resolve error: {error_code}')
        return followups
