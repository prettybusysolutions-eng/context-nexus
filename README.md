# Context Nexus — Persistent Cross-Session Memory for AI Agents

> **"Memory that survives every session. Intelligence that compounds over time."**

---

## What It Is

Context Nexus is a production-grade **persistent memory and observability layer** for AI agents. It provides structured long-term memory, event logging with correlation IDs, session replay, secrets management, and a marketplace protocol — all accessible via a simple Python subprocess interface from any OpenClaw agent.

**Not a vector database. Not a generic logging library. A purpose-built cognitive infrastructure for AI agents that need persistent identity and compounding intelligence.**

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        AGENT (Aurex)                          │
│   Every session: memory_query → decision → action             │
└─────────────────────────┬───────────────────────────────────┘
                          │ subprocess call
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  NEXUS SERVICE (Python)                       │
│                                                              │
│  ┌────────────┐  ┌────────────┐  ┌─────────────────────┐   │
│  │  Memory    │  │  Logging   │  │    Marketplace     │   │
│  │  Service   │  │  Service   │  │    Service         │   │
│  └────────────┘  └────────────┘  └─────────────────────┘   │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              SQLITE ADAPTER (Encrypted)               │   │
│  │   memories · events · run_summaries · secrets        │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    MARKETPLACE PROTOCOL                      │
│                                                              │
│   Agents declare services · buy from each other              │
│   Revenue splits: 70% operator · 3% ops · 27% improvement    │
│                                                              │
│   Built-in: DenialNet API (claim intelligence)               │
│   Built-in: LeakLock Pro (data leak detection)               │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites
- Python 3.11+
- SQLite (built into Python)
- OpenClaw agent environment
- Optional: Redis (for production multi-instance deployments)

### Installation

```bash
# Install the skill
clawhub install context-nexus --force

# Clone the repo
git clone https://github.com/prettybusysolutions-eng/context-nexus
cd context-nexus

# Run install script
./scripts/install

# Configure
cp .env.example .env
# Set CONTEXT_NEXUS_DB_PATH and CONTEXT_NEXUS_ENCRYPTION_KEY
```

### Basic Usage

```python
from nexus_service import memory_set, memory_get, memory_search

# Store something
memory_set("user_preference", {"theme": "dark", "timezone": "America/New_York"})

# Retrieve it
result = memory_get("user_preference")

# Search across all memories
results = memory_search("theme timezone", limit=5)

# Log an event
log_event("scan_completed", {"scan_id": "abc123", "rows": 15000})

# Distill a run summary
distill_run(session_id="abc123")
```

### OpenClaw Plugin (Auto-Loaded)

Context Nexus registers as an OpenClaw plugin and is automatically available to all agent sessions:

```bash
openclaw plugins list | grep context-nexus
# Should show: context-nexus | openclaw | loaded
```

---

## Core Services

### Memory Service

Structured, encrypted long-term memory storage with TTL support.

```python
# Store with optional TTL (seconds)
memory_set("project_state", {"status": "deployed"}, ttl=86400)

# Get with default
memory_get("project_state")

# Pin important memories (never auto-compacted)
memory_pin("critical_system_config")

# Search semantic or keyword
memory_search("deployment status", limit=10)

# List recent memories
memory_recent(limit=20)

# Forget (delete) a memory
memory_forget("temp_cache")
```

### Logging Service

Event logging with correlation IDs and automatic session tracking.

```python
# Log any event
log_event("api_called", {
    "endpoint": "/patterns/search",
    "cost_cents": 75,
    "pattern_id": "uuid"
})

# Retrieve events
events = list_events(
    event_type="api_called",
    limit=100,
    since="2026-04-01T00:00:00Z"
)

# Get specific event
event = get_event(event_id="uuid")
```

### Distill Service

Run distillation — compresses a session into a structured summary.

```python
# Distill the current run
summary = distill_run(session_id="current")

# Explain a failure
explanation = explain_failure(error_event_id="uuid")

# Compare two runs
comparison = compare_runs(run_a="uuid", run_b="uuid")

# Export a snapshot
snapshot = export_snapshot()
```

### Secrets Service

Encrypted secrets storage with automatic masking in logs.

```python
# Store a secret
secret_store("stripe_key", "sk_live_xxx")

# Retrieve a secret
key = secret_get("stripe_key")

# List all secret names (never values)
names = secret_list()

# Delete a secret
secret_delete("stripe_key")
```

### Marketplace Service

Agent-to-agent service marketplace with automatic revenue splits.

```python
# Declare a service
marketplace_declare_policy({
    "slug": "my-agent-service",
    "name": "My Service",
    "price_amount": 1.00,
    "trigger_signals": ["task_completed"]
})

# List available services
services = marketplace_list_services(category="security")

# Buy a service
receipt = marketplace_buy_service(service_id="uuid", quantity=1)

# Get my earnings
earnings = marketplace_my_earnings()
```

---

## OpenClaw Plugin Interface

Context Nexus registers as an OpenClaw plugin and exposes all services via `nexus_service.py`:

```bash
# Direct CLI usage
nexus_service.py <method> '<params_json>'

nexus_service.py memory_search '{"query": "denial patterns", "limit": 5}'
nexus_service.py log_event '{"event_type": "test", "metadata": {}}'
nexus_service.py marketplace_list_services '{"limit": 10}'
nexus_service.py healthcheck '{}'
```

---

## Data Model

### Memory
| Field | Type | Description |
|-------|------|-------------|
| `id` | String | Primary key (UUID) |
| `key` | String | Memory identifier |
| `value` | Blob | AES-256-GCM encrypted JSON |
| `namespace` | String | Logical grouping |
| `pinned` | Boolean | Never auto-compacted |
| `created_at` | DateTime | Creation time |
| `updated_at` | DateTime | Last update |
| `accessed_at` | DateTime | Last access |
| `ttl_seconds` | Integer | Auto-expiry (nullable) |

### Event
| Field | Type | Description |
|-------|------|-------------|
| `id` | String | Primary key (UUID) |
| `event_type` | String | Event classification |
| `session_id` | String | Associated session |
| `correlation_id` | String | Request trace ID |
| `agent_id` | String | Agent identifier |
| `metadata` | Blob | Encrypted event data |
| `created_at` | DateTime | Event time |

### RunSummary
| Field | Type | Description |
|-------|------|-------------|
| `id` | String | Primary key (UUID) |
| `session_id` | String | Session identifier |
| `started_at` | DateTime | Session start |
| `ended_at` | DateTime | Session end |
| `summary` | Blob | Encrypted summary JSON |
| `tool_count` | Integer | Tools used |
| `error_count` | Integer | Errors encountered |

### Secret
| Field | Type | Description |
|-------|------|-------------|
| `id` | String | Primary key (UUID) |
| `key` | String | Secret name (unique) |
| `value` | Blob | Encrypted secret value |
| `created_at` | DateTime | Creation time |
| `last_accessed` | DateTime | Last retrieval |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `CONTEXT_NEXUS_DB_PATH` | Yes | SQLite DB path, e.g. `~/.openclaw/context-nexus/nexus.db` |
| `CONTEXT_NEXUS_ENCRYPTION_KEY` | Yes | 32-byte hex key for AES-256-GCM |
| `CONTEXT_NEXUS_LOG_LEVEL` | No | `debug`, `info`, `warn`, `error` (default: `info`) |
| `CONTEXT_NEXUS_SESSION_SCOPE` | No | `ephemeral` or `durable` (default: `durable`) |
| `CONTEXT_NEXUS_REDIS_URL` | No | Redis URL for production multi-instance |

---

## Storage

### SQLite Schema

```sql
CREATE TABLE memories (
    id TEXT PRIMARY KEY,
    key TEXT NOT NULL,
    value BLOB NOT NULL,          -- AES-256-GCM encrypted
    namespace TEXT DEFAULT 'default',
    pinned BOOLEAN DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    accessed_at TEXT NOT NULL,
    ttl_seconds INTEGER
);

CREATE TABLE events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    session_id TEXT,
    correlation_id TEXT,
    agent_id TEXT,
    metadata BLOB NOT NULL,       -- AES-256-GCM encrypted
    created_at TEXT NOT NULL
);

CREATE TABLE run_summaries (...);
CREATE TABLE secrets (...);
CREATE TABLE tokens (...);
CREATE TABLE checkpoints (...);
```

### Encryption

All memory values, event metadata, and secrets are encrypted at rest using **AES-256-GCM** with a per-workspace encryption key. The key is stored in the environment variable and is never written to disk unencrypted.

---

## Production Requirements

### Phase 1: Security (Required Before Any Production Use)
- [ ] **Encryption Key Rotation**: Automated rotation of `CONTEXT_NEXUS_ENCRYPTION_KEY` with re-encryption of existing data. Current key is static.
- [ ] **Audit Log for Secrets Access**: Every `secret_get` call logged with caller identity, timestamp, and purpose.
- [ ] **Memory Access Controls**: Namespaced access controls — agents can only read/write to their own namespace unless explicitly shared.
- [ ] **TLS for All Connections**: If Redis is used in production, TLS must be enforced on Redis connections.

### Phase 2: Reliability (Required Before Long-Running Deployments)
- [ ] **Database Backup**: Automated daily SQLite backups to S3/GCS. Current: manual or none.
- [ ] **WAL Mode Verification**: SQLite must run in WAL mode for concurrent read/write. Verify this is set on startup.
- [ ] **Storage Compaction**: Automated compaction job to prevent WAL growth on long-running instances. (Service exists but not cron-scheduled.)
- [ ] **Graceful Degradation**: If Redis is unavailable, the system continues operating without caching — not hard failure.
- [ ] **Migration System**: All schema changes via Alembic or equivalent. No manual ALTER TABLE.

### Phase 3: Observability (Required Before Incident Response)
- [ ] **Structured Metrics**: Prometheus metrics for memory operations/second, event ingestion rate, secret access count, marketplace transactions.
- [ ] **Health Check Endpoint**: `GET /health` that returns DB connectivity, encryption key present, Redis status.
- [ ] **Alerting**: Alert when DB size exceeds threshold, secret access anomalies, marketplace payment failures.
- [ ] **Distributed Tracing**: OpenTelemetry spans for all service calls with correlation IDs propagated through the call chain.

### Phase 4: Scalability (Before Multi-Agent Deployments)
- [ ] **Redis Caching Layer**: Frequently accessed memories cached in Redis with LRU eviction.
- [ ] **Connection Pooling**: SQLite adapted for concurrent multi-process access via WAL + busy_timeout.
- [ ] **Namespace Sharding**: Large workspaces sharded by namespace across multiple SQLite files.
- [ ] **Read Replicas**: Read replicas for analytics queries separate from write primary.

### Phase 5: Marketplace Hardening
- [ ] **Service Level Agreements**: Define uptime SLA for marketplace services. Implement automatic failover for declared services.
- [ ] **Payment Escrow**: Marketplaces payments held in escrow until service delivery confirmed.
- [ ] **Dispute Resolution**: Formal dispute process for failed or incomplete service delivery.
- [ ] **Service Reputation**: Weighted reputation scores for marketplace services based on outcome data.

---

## Project Structure

```
context-nexus/
├── services/
│   ├── memory_service.py      # Memory CRUD + encryption
│   ├── logging_service.py     # Event logging
│   ├── distill_service.py     # Run distillation
│   ├── secrets_service.py     # Encrypted secrets
│   └── marketplace_service.py # Agent marketplace
├── storage/
│   └── sqlite_adapter.py      # SQLite connection + encryption
├── plugin/
│   ├── src/
│   │   ├── index.js           # OpenClaw plugin entry
│   │   └── nexus_service.py   # CLI + IPC interface
│   ├── openclaw.plugin.json   # Plugin manifest
│   └── package.json
├── schemas/
│   └── __init__.py            # Pydantic schemas
├── scripts/
│   ├── install                # Production install
│   ├── smoke_test             # Smoke test suite
│   └── release_hardening_loop.py  # Pre-release validation
├── docs/
│   ├── architecture.md
│   ├── security.md
│   ├── storage.md
│   ├── marketplace-protocol.md
│   ├── operations.md
│   ├── troubleshooting.md
│   ├── examples.md
│   ├── lifecycle.md
│   └── roadmap.md
├── requirements.txt
├── .env.example
├── SPEC.md
├── README.md
└── release-status.json
```

---

## Glossary

| Term | Definition |
|------|------------|
| **Memory** | Encrypted key-value store with TTL and namespace support |
| **Event** | Timestamped, correlated log entry with encrypted metadata |
| **Run Summary** | Distilled summary of a complete agent session |
| **Correlation ID** | UUID that traces a single request across all services |
| **Distillation** | Compression of a session's full context into a structured summary |
| **Marketplace Protocol** | Agent-to-agent service declaration, purchase, and settlement |

---

## License

Proprietary. © 2026 PrettyBusySolutions Engineering. All rights reserved.
