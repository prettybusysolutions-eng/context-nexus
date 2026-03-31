# Context Nexus — ClawHub Skill

**Install:** `clawhub install context-nexus`
**Plugin:** also installable as OpenClaw plugin via `openclaw plugins install`

---

## What it is

Context Nexus is the default memory and observability substrate for OpenClaw agents.
Once installed, it:

1. **Persists memory** — set, search, pin, and retrieve facts between sessions
2. **Logs events** — structured logs with automatic redaction
3. **Stores secrets** — encrypted at rest, no hardcoded API keys
4. **Distills runs** — deterministic summaries after each session
5. **Scores performance** — lightweight run scoring with optimization suggestions

---

## Setup

```bash
# Install the skill (clawhub)
clawhub install context-nexus

# Also install as OpenClaw plugin (for auto-hooks)
openclaw plugins install ~/.clawhub/skills/context-nexus/plugin

# Run bootstrap
cd ~/.clawhub/skills/context-nexus
./scripts/install

# Test
./scripts/smoke_test
```

Add to `~/.openclaw/openclaw.json`:

```json
{
  "plugins": {
    "load": {
      "paths": ["~/.clawhub/skills/context-nexus/plugin"]
    },
    "entries": {
      "context-nexus": {
        "enabled": true
      }
    }
  }
}
```

Then: `openclaw gateway restart`

---

## Usage

Once installed, it runs automatically via hooks. No manual calls required.

For power use:

```
# Store a memory
nexus_memory action=set key=user:pref value="dark mode" scope=durable importance=8

# Search memories
nexus_memory action=search query="preference" limit=5

# Store a secret
nexus_secrets action=store name=openai value=sk-... metadata='{"provider":"openai"}'

# Check failures
nexus_logs action=query_failures

# Explain a failure
nexus_replay action=explain_failure session_id=<id>

# Storage status
nexus_admin action=storage_status
```

---

## Memory scopes

| Scope | Auto-persist | Compaction-protected |
|-------|--------------|---------------------|
| `ephemeral` | Current session | No — first 50 kept |
| `durable` | All sessions | Yes — top 500 kept |
| `pinned` | All sessions | Never deleted |

Importance 9-10 → auto-pinned.

---

## Hooks (automatic)

| Hook | Trigger | What happens |
|------|---------|-------------|
| `before_prompt_build` | Every turn | Recent durable memories injected into context |
| `after_tool_call` | Every tool call | Tool result logged; significant tools auto-distilled |
| `session_end` | Session closes | Distilled run summary saved |
| `on_error` | On any error | Failure logged + error summary created |

---

## Secrets security

- PBKDF2 + HMAC-SHA256 encryption at rest
- Fail-closed: decryption errors return nothing
- Logs automatically redact: Stripe keys, GitHub tokens, bearer tokens, private keys
- `nexus_admin action=healthcheck` verifies storage integrity

---

## Upgrade path

| Stage | Storage | Use case |
|-------|---------|----------|
| 1 (free) | SQLite | Single agent, local |
| 2 | PostgreSQL | Multi-agent, same machine |
| 3 | Shared network DB | Multi-agent, remote |

Set `DATABASE_URL` env var for PostgreSQL. Same adapter, zero code change.

---

## Commands

```bash
./scripts/install        # Bootstrap storage + register plugin
./scripts/smoke_test    # Verify end-to-end
./scripts/verify        # Check config
```

---

## Requirements

- Python 3.8+
- OpenClaw 2026.1+
- SQLite (built-in, no install)
- Optional: PostgreSQL for multi-agent shared memory
