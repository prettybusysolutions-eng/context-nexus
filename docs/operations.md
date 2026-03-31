# Context Nexus — Operations

## Health Monitoring

### Live Healthcheck
```bash
nexus_admin action=healthcheck
```
Returns:
```json
{
  "status": "ok",
  "storage": {
    "db_path": "/path/to/nexus.db",
    "db_size_bytes": 4096,
    "memories": 42,
    "events": 318,
    "run_summaries": 12,
    "secrets": 3
  }
}
```

### Watch Mode (continuous)
```bash
watch -n 5 'nexus_admin action=storage_status'
```

---

## Backup

### Manual Snapshot
```bash
# Copy DB file
cp ~/.openclaw/context-nexus/nexus.db ~/backups/nexus-$(date +%Y%m%d).db

# Export JSON snapshot
nexus_admin action=export_snapshot > ~/backups/nexus-snapshot-$(date +%Y%m%d).json
```

### Automated Backup Script
```bash
#!/bin/bash
BACKUP_DIR=~/backups/nexus
DATE=$(date +%Y%m%d-%H%M%S)
mkdir -p $BACKUP_DIR
cp ~/.openclaw/context-nexus/nexus.db $BACKUP_DIR/nexus-$DATE.db
nexus_admin action=export_snapshot > $BACKUP_DIR/nexus-$DATE.json
# Keep last 7
find $BACKUP_DIR -name "nexus-*.db" -mtime +7 -delete
find $BACKUP_DIR -name "nexus-*.json" -mtime +7 -delete
```

---

## Monitoring

### Storage Growth
```bash
nexus_admin action=storage_status
# db_size_bytes tells you growth rate over time
```

### Memory Usage by Scope
```sql
SELECT scope, COUNT(*) as count, AVG(LENGTH(value)) as avg_size
FROM memories
GROUP BY scope;
```

### Most Active Sessions
```sql
SELECT session_id, COUNT(*) as events
FROM events
WHERE created_at > datetime('now', '-7 days')
GROUP BY session_id
ORDER BY events DESC
LIMIT 10;
```

### Auth Failure Rate
```bash
nexus_logs action=query_failures limit=100
# Count failures vs successful calls
```

---

## Performance Tuning

### Slow Query Diagnosis
```sql
EXPLAIN QUERY PLAN SELECT * FROM memories
WHERE scope = 'durable'
ORDER BY importance DESC
LIMIT 20;
```

### WAL Auto-checkpoint Tuning
```python
# In SQLite: adjust checkpoint threshold
db.execute("PRAGMA wal_autocheckpoint=1000")  # checkpoint every 1000 pages
```

### In-Memory Cache for Frequent Reads
For high-frequency `memory_get`, add:
```python
from functools import lru_cache

@lru_cache(maxsize=500)
def cached_get(key):
    return memory_get(key)
```
Note: only for ephemeral/session data. Durable secrets should not be cached.

---

## Migration

### Migrate SQLite to PostgreSQL
1. Export from SQLite:
   ```bash
   nexus_admin action=export_snapshot > snapshot.json
   ```
2. Set PostgreSQL `DATABASE_URL`
3. Initialize schema (automatic on first run)
4. Import:
   ```bash
   nexus_admin action=import_snapshot data="$(cat snapshot.json)"
   ```
5. Verify counts match

### Schema Migration
Migrations run automatically on startup:
```python
def get_current_version(db):
    try:
        return db.execute("SELECT version FROM schema_version").fetchone()[0]
    except Exception:
        return 0

def apply_migrations(db):
    current = get_current_version(db)
    for migration in MIGRATIONS[current:]:
        db.execute(migration)
        db.execute("UPDATE schema_version SET version = ?", [current + 1])
```

---

## Upgrading

### Patch Release
```bash
cd ~/.clawhub/skills/context-nexus
git pull
./scripts/install  # re-run to apply any new migrations
openclaw gateway restart
```

### Major Release
1. Read `CHANGELOG.md`
2. Export snapshot
3. Pull new version
4. Run migrations
5. Verify healthcheck
6. Restart gateway

---

## Capacity Planning

### SQLite Limits
- Max DB size: depends on disk (2TB typical)
- Max rows per table: 2^64
- Recommended max memory: 1GB working set

### When to Move to PostgreSQL
- > 5 agents sharing memory
- > 100k events per day
- > 1GB total data
- Multi-region deployment
- Audit/compliance requiring network-accessible logging

---

## Alerting

Set up alerts on:
- `healthcheck` returns non-ok
- `db_size_bytes` exceeds threshold (e.g., 500MB)
- `query_failures` count spikes (threshold: 10 failures/minute)
- Disk free space < 1GB

```bash
# Example: alert if healthcheck fails
nexus_admin action=healthcheck || echo "ALERT: healthcheck failed" | mail admin@example.com
```
