# Context Nexus Architecture

## Overview

Context Nexus sits between the OpenClaw runtime and the external world. It intercepts lifecycle events, persists structured state to SQLite, and exposes that state back to agents via tools.

```
OpenClaw Runtime
    │
    ├─ hooks: before_prompt_build, after_tool_call, session_end, on_error
    │
    ▼
Context Nexus Plugin (Node.js)
    │
    ├─ registers tools: nexus_memory, nexus_logs, nexus_secrets, nexus_replay, nexus_admin
    │
    ▼
nexus_service.py (Python subprocess)
    │
    ├─ MemoryService → SQLite
    ├─ LoggingService → SQLite
    ├─ SecretsService → SQLite (encrypted)
    ├─ AuthService → SQLite (token_registry)
    └─ DistillService → SQLite (run_summaries)
```

## Storage

SQLite is the default. Schema is initialized on first use.

Tables:
- `memories` — key/value with scope, importance, TTL, tags, source tracking
- `events` — structured log with correlation ids, error classification, redaction
- `run_summaries` — distilled run records with score components
- `secrets` — encrypted credentials with metadata
- `checkpoints` — session checkpoint snapshots
- `token_registry` — OAuth/token lifecycle state

## Secrets encryption

Rolled XOR with PBKDF2-derived keys:
- `encryption_key` from env → PBKDF2 → 32-byte AES-equivalent key
- Separate HMAC key for integrity signatures
- Fail-closed: any decryption error returns None

## Hook semantics

**before_prompt_build**:
- Runs after session load, before prompt is built
- Injects recent durable memories as `prependContext`
- No model call required — pure retrieval

**after_tool_call**:
- Fires after every tool result
- Logs to events table
- Auto-distills on significant tools: exec, write, edit, commit, deploy, browser, git

**session_end**:
- Fires when session closes
- Creates distilled run summary
- Captures last message as result_summary

**on_error**:
- Fires on any error
- Creates failure event + error summary
- Triggers scoring

## Distillation

Deterministic extraction — never blocks on a model call:
1. Extract tool names via regex
2. Extract file paths and URLs
3. Extract error codes and messages
4. Extract next steps and follow-ups
5. Compose action_summary and result_summary

Optional model-assisted compression with token budget and timeout guard.

## Scoring

Composite: `success × 0.5 + efficiency × 0.25 + memory × 0.25`

Suggestions generated from:
- `success == false` → "Investigate failure cause"
- `retry_count > 3` → "High retry count"
- `error_burden > 5` → "High error burden"

## Failure classification

Auth errors classified into 8 types:
- `missing_credential` — no key in storage or env
- `expired_token` — past expiry time
- `refresh_failed` — refresh attempt errored
- `forbidden` — 403 from API
- `invalid_token` — 401 but not expired
- `rate_limited` — 429
- `transport_error` — network/connectivity
- `unknown_auth_state` — unclassified

Each maps to a specific recovery action.

## Compaction policy

- Ephemeral: keep top 50 by importance, delete rest
- Durable: keep top 500 by importance, delete rest
- Pinned: never deleted
- Runs on every 100th `after_tool_call` event

## Upgrades

| Phase | Storage | Adapter |
|-------|---------|---------|
| SQLite (now) | File | `sqlite_adapter.py` |
| PostgreSQL | Network | `postgres_adapter.py` (future) |

Interface is identical. Swap adapter by setting `DATABASE_URL`.
