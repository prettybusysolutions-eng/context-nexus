#!/usr/bin/env python3
"""
Context Nexus — Release Hardening Loop
Autonomous: runs until READY_TO_PUBLISH or BLOCKED_WITH_EXACT_CAUSE
"""
import json, os, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/Users/marcuscoarchitect/.openclaw/agents/aurex/workspace/projects/context-nexus')
STATUS_PATH = ROOT / 'release-status.json'
LOG_PATH = ROOT / 'release-hardening.log'
DB_PATH = ROOT / '.release-hardening.sqlite'
PYTHON = sys.executable or 'python3'

REQUIRED_DOCS = {
    'README.md': ROOT / 'README.md',
    'skill/SKILL.md': ROOT / 'skill' / 'SKILL.md',
    'docs/architecture.md': ROOT / 'docs' / 'architecture.md',
    'docs/examples.md': ROOT / 'docs' / 'examples.md',
    'docs/troubleshooting.md': ROOT / 'docs' / 'troubleshooting.md',
    'docs/lifecycle.md': ROOT / 'docs' / 'lifecycle.md',
    'docs/storage.md': ROOT / 'docs' / 'storage.md',
    'docs/security.md': ROOT / 'docs' / 'security.md',
    'docs/operations.md': ROOT / 'docs' / 'operations.md',
    'docs/roadmap.md': ROOT / 'docs' / 'roadmap.md',
}

REQUIRED_RUNTIME = {
    'plugin/openclaw.plugin.json': ROOT / 'plugin' / 'openclaw.plugin.json',
    'plugin/package.json': ROOT / 'plugin' / 'package.json',
    'plugin/src/index.js': ROOT / 'plugin' / 'src' / 'index.js',
    'plugin/src/nexus_service.py': ROOT / 'plugin' / 'src' / 'nexus_service.py',
    'storage/sqlite_adapter.py': ROOT / 'storage' / 'sqlite_adapter.py',
    'services/memory_service.py': ROOT / 'services' / 'memory_service.py',
    'services/logging_service.py': ROOT / 'services' / 'logging_service.py',
    'services/secrets_service.py': ROOT / 'services' / 'secrets_service.py',
    'services/distill_service.py': ROOT / 'services' / 'distill_service.py',
    'schemas/__init__.py': ROOT / 'schemas' / '__init__.py',
    'scripts/install': ROOT / 'scripts' / 'install',
    'scripts/smoke_test': ROOT / 'scripts' / 'smoke_test',
    'scripts/release_hardening_loop.py': ROOT / 'scripts' / 'release_hardening_loop.py',
}


def now():
    return datetime.now(timezone.utc).isoformat()


def log(msg):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, 'a') as f:
        f.write(f"[{now()}] {msg}\n")


def run(cmd, cwd=ROOT, timeout=180):
    env = os.environ.copy()
    env['CONTEXT_NEXUS_DB_PATH'] = str(DB_PATH)
    p = subprocess.run(cmd, cwd=str(cwd), env=env, text=True, capture_output=True, timeout=timeout)
    return {'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}


def check_files(paths_dict):
    missing = []
    for name, p in paths_dict.items():
        if not p.exists():
            missing.append(name)
    return missing


def validate_json(path):
    try:
        with open(path) as f:
            json.load(f)
        return True, None
    except Exception as e:
        return False, str(e)


def artifact_integrity():
    missing_docs = check_files(REQUIRED_DOCS)
    missing_runtime = check_files(REQUIRED_RUNTIME)
    plugin_json_valid, plugin_json_err = validate_json(ROOT / 'plugin' / 'openclaw.plugin.json')
    return {
        'missing_docs': missing_docs,
        'missing_runtime': missing_runtime,
        'plugin_json_valid': plugin_json_valid,
        'plugin_json_error': plugin_json_err,
        'doc_count': len(REQUIRED_DOCS) - len(missing_docs),
        'runtime_count': len(REQUIRED_RUNTIME) - len(missing_runtime),
        'ok': not missing_docs and not missing_runtime and plugin_json_valid,
    }


def local_health():
    svc = ROOT / 'plugin' / 'src' / 'nexus_service.py'
    out = run([PYTHON, str(svc), 'healthcheck', '{}'], timeout=60)
    ok = out['returncode'] == 0
    parsed = None
    if ok:
        try:
            parsed = json.loads(out['stdout'])
        except Exception:
            ok = False
    return {'ok': ok, 'parsed': parsed, 'stderr': out['stderr'][-500:]}


def run_smoke():
    smoke = ROOT / 'scripts' / 'smoke_test'
    if not smoke.exists():
        return {'ok': False, 'reason': 'smoke_missing'}
    out = run(['bash', str(smoke)], timeout=300)
    return {
        'ok': out['returncode'] == 0,
        'returncode': out['returncode'],
        'stdout_tail': out['stdout'][-3000:],
        'stderr_tail': out['stderr'][-1000:],
    }


def classify(integrity, health, smoke):
    blockers = []
    if not integrity['ok']:
        if integrity['missing_docs']:
            blockers.append({'type': 'missing_docs', 'items': integrity['missing_docs']})
        if integrity['missing_runtime']:
            blockers.append({'type': 'missing_runtime', 'items': integrity['missing_runtime']})
        if not integrity['plugin_json_valid']:
            blockers.append({'type': 'plugin_manifest_invalid', 'error': integrity['plugin_json_error']})
    if not health['ok']:
        blockers.append({'type': 'health_failed', 'stderr': health['stderr']})
    if not smoke['ok']:
        blockers.append({'type': 'smoke_failed', 'stderr_tail': smoke['stderr_tail']})

    if blockers:
        return 'BLOCKED_WITH_EXACT_CAUSE', blockers
    return 'READY_FOR_PUBLISH_VALIDATION', []


def main():
    log('loop_start')
    integrity = artifact_integrity()
    health = local_health()
    smoke = run_smoke()
    state, blockers = classify(integrity, health, smoke)

    status = {
        'updated_at': now(),
        'state': state,
        'integrity': integrity,
        'health': health,
        'smoke': smoke,
        'blockers': blockers,
    }

    if state == 'READY_FOR_PUBLISH_VALIDATION':
        status['next_action'] = 'clawhub_publish_validation'
    else:
        status['next_action'] = 'fix_blockers'

    with open(STATUS_PATH, 'w') as f:
        json.dump(status, f, indent=2)
        f.write('\n')
    log(f'loop_end state={state}')
    print(json.dumps(status, indent=2))


if __name__ == '__main__':
    main()
