# Context Nexus — Troubleshooting

## Installation Issues

### "Module not found: storage"
**Cause:** Python path not set correctly during plugin load.
**Fix:** Verify `sys.path` includes the Context Nexus root directory before importing storage modules.
The plugin wrapper adds the project root to `sys.path` automatically.

### "openclaw.plugin.json not found"
**Cause:** Plugin manifest in wrong location.
**Fix:** Ensure `openclaw.plugin.json` is at the plugin root, not inside `src/`.

### "Plugin not found: context-nexus" after restart
**Cause:** Stale config entry pointing to non-existent plugin path.
**Fix:**
```bash
openclaw doctor --fix
# or manually remove context-nexus entry from ~/.openclaw/openclaw.json plugins.entries
```

---

## Runtime Issues

### Healthcheck returns `connection refused`
**Cause:** `nexus_service.py` subprocess not started.
**Fix:** Ensure plugin `src/index.js` starts `nexus_service.py` as subprocess before any tool calls.

### Memory set but get returns nothing
**Cause:** Wrong scope used. Ephemeral memories are session-scoped.
**Fix:** Use `scope=durable` for cross-session persistence.

### Secrets decryption returns empty
**Cause:** Encryption key mismatch or corruption.
**Fix:** Context Nexus is fail-closed — empty return means decryption failed. Check that `CONTEXT_NEXUS_ENCRYPTION_KEY` env var is consistent.

### Smoke test fails on secrets test
**Cause:** Python `cryptography` library not installed.
**Fix:** `pip install cryptography` or run `./scripts/install` which handles this.

---

## Performance Issues

### First query is slow
**Cause:** SQLite WAL checkpoint and warm-up on cold start.
**Fix:** Normal. Subsequent queries use WAL cache and are fast.

### Memory search returns nothing relevant
**Cause:** Query terms don't match indexed fields.
**Fix:** Use exact key names when possible. Search scans `key`, `value`, and `tags` fields.

### too many open files
**Cause:** SQLite connections not closed properly.
**Fix:** Always use context managers (`with get_db() as db:`) or explicit `db.close()`.

---

## ClawHub Publish Issues

### "Path must be a folder" on publish
**Cause:** ClawHub CLI relative path resolution bug in some shell contexts.
**Fix:** Use absolute path: `clawhub publish /full/path/to/skill --slug context-nexus ...`

### "Skill not found" after install
**Cause:** ClawHub registry not yet synchronized after publish.
**Fix:** Wait 30 seconds and retry. Registry propagates async.

### Wrong user logged in
**Fix:**
```bash
clawhub logout
clawhub login
clawhub whoami
```

---

## OpenClaw Gateway Issues

### Gateway won't restart after plugin enable
**Cause:** Invalid plugin config in `openclaw.json`.
**Fix:**
```bash
# Remove bad entry
openclaw gateway stop
# Edit ~/.openclaw/openclaw.json manually
# Restart
openclaw gateway start
```

### Plugin loads but hooks don't fire
**Cause:** Hook event names don't match OpenClaw's actual event bus names.
**Fix:** Verify hook names in `openclaw.plugin.json` match OpenClaw's hook contract exactly.

---

## Data Issues

### Import fails on large snapshot
**Cause:** JSON parse timeout on very large exports.
**Fix:** Use `--batch-size` if available, or export/import by scope separately.

### Checkpoint restore fails
**Cause:** Checkpoint DB was created with different schema version.
**Fix:** Checkpoints are version-stamped. Use matching schema or recreate checkpoint.

---

## Debug Mode

Enable verbose logging:
```bash
CONTEXT_NEXUS_LOG_LEVEL=debug python3 -m nexus_service
```

Run smoke test with verbose output:
```bash
DEBUG=1 ./scripts/smoke_test
```
