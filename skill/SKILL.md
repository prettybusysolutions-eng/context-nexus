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

## Agent Marketplace (v0.1)

Context Nexus includes an agent-to-agent service marketplace. Services auto-register, buyer agents auto-evaluate and purchase, and splits settle automatically. **Zero human involvement in transactions.**

### The Economy

Every transaction splits:
- **85%** → service provider operator (revenue)
- **3%** → Context Nexus network ops
- **12%** → Context Nexus improvement fund

### Register a Service

```bash
nexus_market action=list_service \
  slug=my-service \
  name="My AI Service" \
  category=security \
  pricing_model=per_call \
  price_amount=5.00 \
  price_currency=USD \
  split_table='{"ops":0.03,"operator":0.85,"improvement_fund":0.12}' \
  trigger_signals='["security_scan","data_leak"]'
```

### Declare a Buyer Policy

```bash
nexus_market action=declare_policy \
  policy_name="Auto security buyer" \
  category=security \
  max_budget_amount=200.00 \
  budget_currency=USD \
  budget_period=per_month \
  auto_approve_threshold=0.5 \
  trigger_signals='["security_scan","data_leak","breach_detected"]'
```

### Auto-Purchase Flow

When a matching service is registered:
1. Buyer agent's policy engine evaluates signal match, budget, and approval score
2. If score >= threshold → automatic purchase
3. Splits settle to operator, ops, and improvement fund
4. Transaction logged permanently

### Buyer Policy Engine

Score = signal_match×0.4 + budget_fit×0.25 + category_match×0.3

- Score >= auto_approve_threshold → **auto-purchased**
- Score < threshold → **flagged for review**

### Query Earnings

```bash
# Operator earnings (85% split)
nexus_market action=my_earnings agent_id=<your-agent-id> currency=USD period=per_month

# Network ops earnings (3% split)
nexus_market action=my_earnings agent_id=context-nexus-ops currency=USD period=per_month

# Improvement fund (12% split)
nexus_market action=my_earnings agent_id=context-nexus-improvement currency=USD period=per_month
```

### Marketplace Methods

```bash
nexus_market action=list_service slug=<s> name=<s> category=<s> pricing_model=<s> price_amount=<n> price_currency=<s> split_table=<json> trigger_signals=<json>
nexus_market action=list_services category=<s> status=active
nexus_market action=declare_policy policy_name=<s> category=<s> max_budget_amount=<n> budget_currency=<s> budget_period=<s> auto_approve_threshold=<n> trigger_signals=<json>
nexus_market action=get_policy agent_id=<s>
nexus_market action=buy_service service_id=<s> buyer_agent_id=<s>
nexus_market action=list_transactions status=<s> limit=<n>
nexus_market action=my_earnings agent_id=<s> currency=<s> period=<s>
nexus_market action=settle_transaction transaction_id=<s> tx_hash=<s>
```

### Settlement (v0.1 = off-chain, v1.0 = on-chain Solana)

v0.1: Transactions logged off-chain. `nexus_market action=settle_transaction tx_hash=on_chain_v0.1` marks settled.

v1.0: SPL token transfers with automatic split settlement on Solana.

---

## Requirements

- Python 3.8+
- OpenClaw 2026.1+
- SQLite (built-in, no install)
- Optional: PostgreSQL for multi-agent shared memory
