# Context Nexus — Examples

## Memory Examples

### Store a durable fact
```
nexus_memory action=set key=user:project value="LeakLock SaaS v1" scope=durable importance=8
```

### Store an ephemeral session note
```
nexus_memory action=set key=session:todo value="Verify Stripe webhook" scope=ephemeral importance=5
```

### Retrieve a specific memory
```
nexus_memory action=get key=user:project
```

### Search memories by topic
```
nexus_memory action=search query="Stripe" limit=10
nexus_memory action=search query="memory" scope=durable importance=7
```

### Pin an important memory
```
nexus_memory action=pin key=user:api_key is_pinned=true
```

### Forget a memory
```
nexus_memory action=forget key=session:debug
```

### Export all data
```
nexus_admin action=export_snapshot
```

---

## Secrets Examples

### Store an API key
```
nexus_secrets action=store name=openai value=sk-... metadata='{"provider":"openai","model":"gpt-4"}'
```

### Retrieve a secret
```
nexus_secrets action=get name=openai
```

### List all secret names (no values exposed)
```
nexus_secrets action=list
```

### Delete a secret
```
nexus_secrets action=delete name=stale_key
```

---

## Observability Examples

### Query auth failures
```
nexus_logs action=query_failures limit=20
```

### Query events by session
```
nexus_logs action=list_events session_id=<session-id>
```

### Get session timeline
```
nexus_logs action=session_timeline session_id=<session-id>
```

### Explain a specific failure
```
nexus_replay action=explain_failure session_id=<failure-session-id>
```

---

## Run Distillation Examples

### Distill current session
```
nexus_replay action=distill_run goal="Deploy LeakLock to Render"
```

### Compare two runs
```
nexus_replay action=compare_runs session_id_a=<id1> session_id_b=<id2>
```

### Score a run
```
nexus_replay action=score_run session_id=<id>
```

---

## Hook-Driven Usage (Automatic)

Hooks fire without manual calls:

### before_prompt_build
Your agent automatically retrieves durable memories before every response:
```json
{"action": "before_prompt_build", "session_id": "abc123"}
```

### after_tool_call
Tool calls are logged automatically:
```json
{"action": "after_tool_call", "tool": "exec", "session_id": "abc123", "result": "..."}
```

### session_end
Session automatically distilled on close:
```json
{"action": "session_end", "session_id": "abc123", "goal": "..."}
```

### on_error
Failures logged and explained automatically:
```json
{"action": "on_error", "error": "insufficient_quota", "session_id": "abc123"}
```

---

## Operational Examples

### Healthcheck
```
nexus_admin action=healthcheck
```

### Storage status
```
nexus_admin action=storage_status
```

### Compaction (manual trigger)
```
nexus_admin action=compact
```

### Reset a session
```
nexus_admin action=reset_session session_id=<id>
```

### Wipe all data
```
nexus_admin action=wipe scope=all
```
