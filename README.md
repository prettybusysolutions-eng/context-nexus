# Context Nexus

**Persistent cross-session memory, structured observability, and secrets management for OpenClaw agents.**

Local-first SQLite by default. No mandatory cloud. No setup before value.

---

## What it does

- **Memory**: Set, get, search, pin, and forget facts across sessions
- **Observability**: Every run is logged with structured events, redaction, and session timelines
- **Secrets**: Encrypted credential storage — no hardcoded API keys
- **Replay**: Inspect what happened, why it failed, and what context was loaded
- **Scoring**: Lightweight performance scoring per run
- **Hooks**: Integrates with OpenClaw lifecycle — `before_prompt_build`, `after_tool_call`, `session_end`, `on_error`

---

## Install

```bash
git clone https://github.com/prettybusysolutions-eng/context-nexus.git
cd context-nexus
./scripts/install
```

Then add to `~/.openclaw/openclaw.json`:

```json
{
  "plugins": {
    "load": {
      "paths": ["~/.openclaw/plugins/context-nexus"]
    },
    "entries": {
      "context-nexus": {
        "enabled": true
      }
    }
  }
}
```

Then:
```bash
openclaw gateway restart
./scripts/smoke_test
```

---

## Tools

### `nexus_memory`
```json
{ "action": "set",    "key": "user:name",  "value": "Kamm",   "scope": "durable", "importance": 8 }
{ "action": "get",    "key": "user:name",  "scope": "durable" }
{ "action": "search", "query": "user",     "limit": 10 }
{ "action": "recent", "scope": "durable",  "limit": 5 }
{ "action": "pin",    "key": "user:name",  "pinned": true }
{ "action": "forget", "key": "user:name" }
{ "action": "compact" }
```

### `nexus_logs`
```json
{ "action": "list_events",     "session_id": "abc", "limit": 20 }
{ "action": "query_failures",  "limit": 10 }
{ "action": "summarize_session", "session_id": "abc" }
```

### `nexus_secrets`
```json
{ "action": "store", "name": "openai", "value": "sk-...", "metadata": {"provider": "openai"} }
{ "action": "get",   "name": "openai" }
{ "action": "list" }
{ "action": "delete", "name": "openai" }
```

### `nexus_replay`
```json
{ "action": "session_timeline", "session_id": "abc", "limit": 20 }
{ "action": "explain_failure",  "session_id": "abc" }
{ "action": "compare_runs",    "limit": 10 }
{ "action": "show_loaded_context", "session_id": "abc" }
```

### `nexus_admin`
```json
{ "action": "healthcheck" }
{ "action": "storage_status" }
{ "action": "run_compaction" }
{ "action": "export_snapshot" }
```

---

## Auto-memory (hooks)

Context Nexus hooks run automatically on OpenClaw lifecycle events:

| Hook | What it does |
|------|-------------|
| `before_prompt_build` | Injects recent durable memories into context |
| `after_tool_call` | Logs tool calls + auto-distills significant actions |
| `session_end` | Saves a distilled run summary |
| `on_error` | Logs the failure + creates an error summary |

---

## Memory scopes

| Scope | Lifetime | Examples |
|-------|----------|----------|
| `ephemeral` | Short-lived | current subtask, temp assumptions |
| `durable` | Reusable | user preferences, architecture decisions |
| `pinned` | Must-survive | core system direction, critical truths |

Importance 1-10. Importance ≥ 9 auto-pins. Pinned memories survive compaction.

---

## Secrets security

- Encrypted at rest with PBKDF2 key derivation + HMAC signature
- Fail-closed: decryption failure returns nothing, never leaks
- Redacted in logs: Stripe keys, GitHub tokens, bearer tokens, private keys
- Auth failure classification: expired, refresh_failed, forbidden, invalid, rate_limited, transport_error

---

## Upgrade path

1. **Local SQLite** (default) → works offline, zero config
2. **PostgreSQL** → set `DATABASE_URL` env var, same adapter interface
3. **Multi-agent shared memory** → same DB, multiple agents connect via network

---

## File structure

```
context-nexus/
├── README.md
├── LICENSE
├── schemas/
│   └── __init__.py         ← SQL migrations
├── storage/
│   └── sqlite_adapter.py   ← SQLite storage engine
├── services/
│   ├── memory_service.py    ← Memory CRUD + distillation
│   ├── logging_service.py   ← Structured event logging
│   ├── secrets_service.py  ← Encrypted secrets + auth helpers
│   └── distill_service.py  ← Deterministic run summarization
├── plugin/
│   ├── openclaw.plugin.json
│   ├── package.json
│   └── src/
│       ├── index.js         ← OpenClaw plugin + tools
│       └── nexus_service.py ← Python IPC bridge
├── scripts/
│   ├── install             ← Bootstrap + register
│   ├── smoke_test          ← End-to-end verification
│   └── verify              ← Config validation
└── docs/
    ├── architecture.md
    ├── security.md
    └── operations.md
```
