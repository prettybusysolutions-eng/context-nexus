# Context Nexus — Roadmap

## v0.1 (Current)
- [x] SQLite storage engine with 6 tables
- [x] Memory CRUD with scope and importance
- [x] Encrypted secrets storage (PBKDF2+XOR+HMAC)
- [x] Structured event logging with redaction
- [x] Deterministic run distillation
- [x] 5 OpenClaw hooks registered
- [x] 5 tool surfaces exposed
- [x] Auth failure 8-class classification
- [x] 18 smoke tests
- [x] ClawHub skill wrapper (basic)
- [x] Local plugin install path

## v0.2 — Publish Ready
- [ ] Rich SKILL.md with all docs linked
- [ ] ClawHub publish validated
- [ ] OpenClaw plugin load proven end-to-end
- [ ] Unit test suite (>80% coverage on storage, services)
- [ ] Integration test suite (hook firing, cross-session retrieval)
- [ ] `examples.md`, `troubleshooting.md`, `lifecycle.md`, `storage.md`, `security.md`, `operations.md` (this document)

## v0.3 — Multi-Agent Support
- [ ] PostgreSQL adapter (same schema, network transport)
- [ ] Shared durable memory across agents
- [ ] Token registry for cross-agent credential sharing
- [ ] Lock manager for concurrent writes
- [ ] Cross-agent event bus (optional, for tightly coupled agents)

## v0.4 — Observability Dashboard
- [ ] Web UI: memory explorer
- [ ] Web UI: event timeline
- [ ] Web UI: run score history
- [ ] Web UI: secret audit log
- [ ] Usage metrics: memories/day, events/day, API calls/day

## v0.5 — Advanced Intelligence
- [ ] Semantic memory search (embeddings-based)
- [ ] Run similarity scoring (find similar past runs)
- [ ] Anomaly detection (unusual error patterns)
- [ ] Proactive suggestion engine (based on distilled run patterns)
- [ ] Model-assisted compression (optional, budget-controlled)

## v1.0 — Production Grade
- [ ] Horizontal scaling (Stateless adapter + shared DB)
- [ ] SSO / OAuth integration
- [ ] Audit log export (SOC2/ISO27001 compatible)
- [ ] SLA monitoring (uptime, latency p50/p99)
- [ ] Encryption key rotation without data loss
- [ ] Managed cloud tier (Context Nexus Cloud)

---

## Future Monetization Tiers

### Free (v0.1)
- Single agent
- Local SQLite
- 500 durable memories
- 50 events/day

### Pro ($15/mo)
- Single agent
- Local or PostgreSQL
- Unlimited memories
- Unlimited events
- Basic dashboard
- Email support

### Team ($50/mo per agent)
- Multi-agent shared memory
- PostgreSQL required
- Unlimited agents
- Advanced dashboard
- Audit logs
- SSO
- Priority support

### Enterprise (custom)
- Everything in Team
- Managed cloud option
- Custom SLA
- Dedicated infra
- On-premise option

---

## Deprecations

### Deprecated in v0.x
- None yet

### Deprecated in v1.0
- `scope=session` → renamed to `scope=ephemeral` (v0.2)
- Direct `nexus_service.py` CLI args → use JSON stdin (v0.2)

---

## Known Issues

- [ ] `memory_search` uses LIKE/FTS, not semantic similarity (v0.5)
- [ ] No concurrent write locking in SQLite mode (PostgreSQL only in v0.3)
- [ ] Encryption key rotation requires re-encryption of all secrets (manual in v0.x)
- [ ] No TTL enforcement on ephemeral memories (compaction only on count)
