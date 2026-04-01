#!/usr/bin/env python3
"""
Automated SQLite backup for Context Nexus.
Run via cron: 0 2 * * * /path/to/backup.py

Retains the 7 most recent backups. Run manually or via cron.
Usage: python3 scripts/backup.py
"""
import os
import sys
import shutil
import datetime

DB_PATH = os.environ.get(
    'CONTEXT_NEXUS_DB_PATH',
    os.path.expanduser('~/.openclaw/context-nexus/nexus.db')
)
BACKUP_DIR = os.path.expanduser('~/.openclaw/context-nexus/backups')
KEEP = 7


def run_backup():
    if not os.path.exists(DB_PATH):
        print(f'[BACKUP] DB not found at {DB_PATH} — skipping')
        return None

    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    dest = os.path.join(BACKUP_DIR, f'nexus_backup_{ts}.db')
    shutil.copy2(DB_PATH, dest)
    print(f'[BACKUP] Saved: {dest}')

    # Prune old backups
    backups = sorted([
        f for f in os.listdir(BACKUP_DIR)
        if f.startswith('nexus_backup_') and f.endswith('.db')
    ])
    removed = 0
    for old in backups[:-KEEP]:
        path = os.path.join(BACKUP_DIR, old)
        os.remove(path)
        removed += 1
        print(f'[BACKUP] Removed: {old}')

    print(f'[BACKUP] Done. {len(backups)} total backups, {removed} removed.')
    return dest


if __name__ == '__main__':
    run_backup()
