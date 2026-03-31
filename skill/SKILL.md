---
name: context-nexus
description: "Persistent cross-session memory, structured observability, encrypted secrets management, and replay for OpenClaw agents. Local-first SQLite. Installs as both skill and OpenClaw plugin. Use when: (1) agents need memory between sessions, (2) API keys need secure storage, (3) run history needs replay and analysis, (4) auth failures need classification and recovery."
metadata:
  {
    "openclaw":
      {
        "emoji": "🧠",
        "requires": { "bins": ["python3"] },
        "install":
          [
            {
              "id": "context-nexus-repo",
              "kind": "clone",
              "url": "https://github.com/prettybusysolutions-eng/context-nexus",
              "label": "Clone Context Nexus repo",
            },
          ],
      },
  }
---

# Context Nexus

Persistent memory, observability, secrets management, and replay for OpenClaw agents.

## What it is

Context Nexus is the default memory and observability substrate for OpenClaw agents.
Once installed, it:

1. **Persists memory** — set, search, pin, and retrieve facts between sessions
2. **Logs events** — structured logs with automatic redaction
3. **Stores secrets** — encrypted at rest, no hardcoded API keys
4. **Distills runs** — deterministic summaries after each session
5. **Scores performance** — lightweight run scoring with optimization suggestions

---

## Install

```bash
# Step 1: Clone the repo (runtime + plugin)
git clone https://github.com/prettybusysolutions-eng/context-nexus ~/context-nexus

# Step 2: Bootstrap storage
cd ~/context-nexus
./scripts/install

# Step 3: Install as OpenClaw plugin
openclaw plugins install ~/context-nexus/plugin

# Step 4: Add to openclaw.json plugins.entries
# (edit ~/.openclaw/openclaw.json — see Setup section above)

# Step 5: Restart gateway
openclaw gateway restart

# Verify
./scripts/smoke_test
```

**Note:** `clawhub install context-nexus` installs this SKILL.md + metadata only.
The full runtime (plugin, services, storage) requires the GitHub clone above.

---

## Setup

After install, add plugin to `~/.openclaw/openclaw.json`:

```json
{
  "plugins": {
    "load": {
      "paths": ["~/context-nexus/plugin"]
    },
    "entries": {
      "context-nexus": {
        "enabled": true,
        "config": {
          "sessionScope": "durable",
          "logLevel": "info"
        }
      }
    }
  }
}
```

Then: `openclaw gateway restart`

---

## Usage (automatic hooks)

Once installed, it runs automatically via hooks. No manual calls required for standard use.

**Hooks that fire automatically:**
- `before_prompt_build` — injects recent durable memories before every response
- `after_tool_call` — logs every tool call with redaction
- `session_end` — distills run summary automatically
- `on_error` — logs and classifies failures

**Manual power use:**

```bash
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
nexus_admin action=healthcheck
```

---

## Memory scopes

| Scope | Lifetime | Compaction |
|-------|----------|------------|
| `ephemeral` | Current session only | Top 50 kept |
| `durable` | All sessions | Top 500 kept |
| `pinned` | Permanent | Never deleted |

Importance 9-10 → auto-pinned.

---

## Secrets security

- PBKDF2 + HMAC-SHA256 encryption at rest
- Fail-closed: decryption errors return nothing
- Logs automatically redact Stripe keys, GitHub tokens, bearer tokens, private keys, JWTs
- `nexus_admin action=healthcheck` verifies storage integrity

---

## Architecture

- Node.js plugin registers hooks + exposes tools to OpenClaw
- Python subprocess handles all storage/logic (`nexus_service.py`)
- SQLite default; PostgreSQL supported via `DATABASE_URL`
- Zero mandatory cloud dependencies

---

## Storage

Default: `~/.openclaw/context-nexus/nexus.db`

PostgreSQL (optional): set `DATABASE_URL`

Upgrade path: same adapter, zero code change.

---

## Docs

- [Architecture](docs/architecture.md)
- [Examples](docs/examples.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Lifecycle](docs/lifecycle.md)
- [Storage](docs/storage.md)
- [Security](docs/security.md)
- [Operations](docs/operations.md)
- [Roadmap](docs/roadmap.md)

---

## Requirements

- Python 3.8+
- OpenClaw 2026.1+
- SQLite (built-in, no install)
- Optional: PostgreSQL for multi-agent shared memory
