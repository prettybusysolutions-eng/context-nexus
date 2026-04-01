#!/usr/bin/env python3
"""
Context Nexus Python Service
Handles all storage, memory, logging, secrets, distillation, and scoring.
Called by the OpenClaw plugin via subprocess.
"""
import sys
import json
import os

# Bootstrap path — find the actual project root with storage/, services/
_plugin_dir = os.path.dirname(os.path.abspath(__file__))  # plugin/src or src
_context_nexus_root = os.path.dirname(os.path.dirname(_plugin_dir))  # → context-nexus/

# If we're running from ~/.openclaw/plugins/context-nexus/src/ the actual source
# repo is at the user's workspace projects path — walk up to find it.
if not os.path.exists(os.path.join(_context_nexus_root, 'storage')):
    # Try one more level up (plugin root → .openclaw → home)
    _context_nexus_root = os.path.dirname(_context_nexus_root)
if not os.path.exists(os.path.join(_context_nexus_root, 'storage')):
    # Fallback: known source location
    _context_nexus_root = '/Users/marcuscoarchitect/.openclaw/agents/aurex/workspace/projects/context-nexus'

if _context_nexus_root not in sys.path:
    sys.path.insert(0, _context_nexus_root)

from storage.sqlite_adapter import SQLiteAdapter
from services.memory_service import MemoryService
from services.logging_service import LoggingService
from services.secrets_service import SecretsService, AuthService
from services.distill_service import DistillService
from services.marketplace_service import MarketplaceService

# Initialize services
_db_path = os.environ.get('CONTEXT_NEXUS_DB_PATH') or os.path.expanduser('~/.openclaw/context-nexus/nexus.db')
os.makedirs(os.path.dirname(_db_path), exist_ok=True)

_storage = SQLiteAdapter(_db_path)
_memory = MemoryService(_storage)
_logging = LoggingService(_storage)
_secrets = SecretsService(_storage)
_auth = AuthService(_storage)
_distill = DistillService()
_marketplace = MarketplaceService(_storage)


def _result(data=None, error=None):
    """Serialize a response."""
    if error:
        return json.dumps({'error': str(error)})
    return json.dumps(data or {'ok': True})


def _fail(error):
    """Serialize an error."""
    return json.dumps({'error': str(error)})


# ── Memory ─────────────────────────────────────────────────────────────────

def memory_set(params):
    return _result(_memory.set(
        key=params['key'],
        value=params['value'],
        scope=params.get('scope', 'durable'),
        importance=params.get('importance', 5),
        session_id=params.get('session_id'),
        thread_id=params.get('thread_id'),
        pinned=params.get('pinned', False),
        ttl_seconds=params.get('ttl_seconds'),
    ))


def memory_get(params):
    val = _memory.get(key=params['key'], scope=params.get('scope'))
    return _result(val)


def memory_search(params):
    results = _memory.search(
        query=params.get('query', ''),
        limit=params.get('limit', 10),
        scope=params.get('scope'),
        session_id=params.get('session_id'),
    )
    return _result(results)


def memory_recent(params):
    results = _memory.recent(
        limit=params.get('limit', 10),
        scope=params.get('scope'),
    )
    return _result(results)


def memory_pin(params):
    return _result(_memory.pin(key=params['key'], pin=params.get('pin', True)))


def memory_forget(params):
    return _result(_memory.forget(key=params['key'], scope=params.get('scope')))


def compact(params):
    deleted = _memory.compact(
        keep_durable=params.get('keep_durable', 500),
        keep_ephemeral=params.get('keep_ephemeral', 50),
    )
    return _result({'deleted': deleted})


# ── Logging ─────────────────────────────────────────────────────────────────

def log_event(params):
    event_id = _logging.log_start(
        event_type=params.get('event_type', 'run'),
        session_id=params.get('session_id'),
        thread_id=params.get('thread_id'),
        correlation_id=params.get('correlation_id'),
        input_summary=params.get('input_summary'),
        payload=params.get('payload'),
    )
    if params.get('status') and params['status'] != 'running':
        _logging.log_end(
            event_id=event_id,
            status=params['status'],
            output_summary=params.get('output_summary'),
            error_code=params.get('error_code'),
            error_message=params.get('error_message'),
        )
    return _result({'event_id': event_id})


def distill_run(params):
    d = _distill.distill(
        goal=params.get('goal', ''),
        input_summary=params.get('input_summary', ''),
        raw_output=params.get('result_summary', ''),
        status='success' if params.get('success') else 'failure',
        tools_used=params.get('tools_used'),
    )
    run_id = _logging.log_run(
        session_id=params.get('session_id', 'unknown'),
        thread_id=params.get('thread_id', 'unknown'),
        goal=d['goal'],
        action_summary=d['action_summary'],
        result_summary=d['result_summary'],
        success=d['success'],
        tools_used=d.get('tools_used'),
    )
    return _result({'run_id': run_id, 'distillation': d})


def list_events(params):
    events = _logging.query_events(
        limit=params.get('limit', 20),
        session_id=params.get('session_id'),
        event_type=params.get('event_type'),
    )
    return _result(events)


def get_event(params):
    events = _logging.query_events(limit=1, session_id=params.get('session_id'))
    return _result(events[0] if events else None)


def query_failures(params):
    return _result(_logging.query_failures(limit=params.get('limit', 20)))


def summarize_session(params):
    return _result(_logging.summarize_session(session_id=params.get('session_id', '')))


# ── Secrets ──────────────────────────────────────────────────────────────────

def secret_store(params):
    ok = _secrets.store(
        name=params['name'],
        value=params['value'],
        metadata=params.get('metadata', {}),
        caller_id='cli',
    )
    return _result({'ok': ok})


def secret_get(params):
    val = _secrets.get(name=params['name'], caller_id='cli')
    return _result({'value': val})


def secret_list(params):
    return _result(_secrets.list_names())


def secret_delete(params):
    return _result({'ok': _secrets.delete(name=params['name'], caller_id='cli')})

def secret_audit_log(params):
    """Get the secrets access audit log. Usage: nexus_service.py secret_audit_log '{"limit": 100}'"""
    limit = params.get('limit', 100)
    resource_type = params.get('resource_type', None)  # 'secret' to filter only secret accesses
    return _result(_secrets._s.get_audit_log(resource_type=resource_type, limit=limit))


# ── Token registry ────────────────────────────────────────────────────────────

def token_set(params):
    return _result(_auth.token_set(
        provider=params['provider'],
        account_name=params['account_name'],
        access_token=params.get('access_token'),
        refresh_token=params.get('refresh_token'),
        access_expires_at=params.get('access_expires_at'),
        refresh_expires_at=params.get('refresh_expires_at'),
        metadata=params.get('metadata', {}),
    ))


def token_status(params):
    return _result(_auth.token_status(
        provider=params['provider'],
        account_name=params['account_name'],
    ))


def token_classify_error(params):
    ec = _auth.classify_error(
        error_code=params.get('error_code'),
        error_message=params.get('error_message'),
        http_status=params.get('http_status'),
    )
    return _result({
        'error_class': ec,
        'description': _auth.describe_error(ec),
    })


# ── Replay ──────────────────────────────────────────────────────────────────

def session_timeline(params):
    session_id = params.get('session_id')
    events = _logging.query_events(limit=params.get('limit', 50), session_id=session_id)
    runs = _storage.run_get(limit=params.get('limit', 20), session_id=session_id)
    return _result({'events': events, 'runs': runs})


def explain_failure(params):
    session_id = params.get('session_id')
    failures = _logging.query_failures(limit=5)
    if not failures:
        return _result({'explanation': 'No failures found'})
    latest = failures[0]
    classification = _auth.classify_error(
        error_code=latest.get('error_code'),
        error_message=latest.get('error_message'),
    )
    return _result({
        'latest_failure': latest,
        'classification': classification,
        'description': _auth.describe_error(classification),
        'suggestion': _get_suggestion(classification),
    })


def compare_runs(params):
    runs = _storage.run_get(limit=params.get('limit', 10))
    scored = [_storage.run_score(r['id']) for r in runs if r.get('id')]
    return _result({'runs': runs, 'scores': scored})


def show_loaded_context(params):
    session_id = params.get('session_id')
    recent_memories = _memory.recent(limit=10)
    return _result({'recent_memories': recent_memories})


def _get_suggestion(error_class):
    suggestions = {
        'expired_token': 'Run: nexus_secrets with action=get for the token, then re-authenticate with the provider.',
        'refresh_failed': 'Token may be revoked. Re-authorize with: openclaw models auth login --provider <name>',
        'forbidden': 'API key lacks required permissions. Check provider dashboard for scope.',
        'invalid_token': 'Token is malformed. Delete and re-store the secret.',
        'rate_limited': 'Back off. Retry after cooldown using exponential backoff.',
        'transport_error': 'Check network connectivity and DNS resolution.',
        'missing_credential': 'Store credential with: nexus_secrets action=store name=<provider>',
    }
    return suggestions.get(error_class, 'Review error details and logs.')


# ── Admin ─────────────────────────────────────────────────────────────────────

def healthcheck(params):
    try:
        status = _storage.storage_status()
        return _result({'status': 'ok', 'storage': status})
    except Exception as e:
        return _fail(str(e))


def storage_status(params):
    return _result(_storage.storage_status())


def export_snapshot(params):
    return _result(_storage.export_snapshot())


# ── Marketplace ────────────────────────────────────────────────────────────────

def marketplace_list_service(params):
    return _result(_marketplace.list_service(
        slug=params['slug'],
        name=params['name'],
        description=params.get('description', ''),
        category=params['category'],
        pricing_model=params['pricing_model'],
        price_amount=float(params['price_amount']),
        price_currency=params.get('price_currency', 'USD'),
        split_table=params['split_table'],
        trigger_signals=params['trigger_signals'],
        provider_agent_id=params.get('provider_agent_id', 'self'),
    ))


def marketplace_get_service(params):
    return _result(_marketplace.get_service(
        service_id=params.get('service_id'),
        slug=params.get('slug'),
    ))


def marketplace_list_services(params):
    return _result(_marketplace.list_services(
        category=params.get('category'),
        status=params.get('status', 'active'),
        limit=params.get('limit', 50),
    ))


def marketplace_declare_policy(params):
    return _result(_marketplace.declare_policy(
        policy_name=params['policy_name'],
        category=params['category'],
        max_budget_amount=float(params['max_budget_amount']),
        budget_currency=params.get('budget_currency', 'USD'),
        budget_period=params.get('budget_period', 'per_month'),
        auto_approve_threshold=float(params['auto_approve_threshold']),
        trigger_signals=params['trigger_signals'],
        agent_id=params.get('agent_id', 'self'),
    ))


def marketplace_get_policy(params):
    return _result(_marketplace.get_policy(agent_id=params.get('agent_id', 'self')))


def marketplace_buy_service(params):
    return _result(_marketplace.buy_service(
        service_id=params['service_id'],
        buyer_agent_id=params.get('buyer_agent_id', 'self'),
        budget_agent_id=params.get('budget_agent_id', 'self'),
    ))


def marketplace_list_transactions(params):
    return _result(_marketplace.list_transactions(
        status=params.get('status'),
        limit=params.get('limit', 50),
    ))


def marketplace_my_earnings(params):
    return _result(_marketplace.my_earnings(
        agent_id=params.get('agent_id', 'self'),
        currency=params.get('currency', 'USD'),
        period=params.get('period', 'per_month'),
    ))


def marketplace_settle_transaction(params):
    return _result(_marketplace.settle_transaction(
        transaction_id=params['transaction_id'],
        tx_hash=params.get('tx_hash', 'off_chain_v0.1'),
    ))


# ── Dispatch ─────────────────────────────────────────────────────────────────

METHOD_MAP = {
    'memory_set': memory_set,
    'memory_get': memory_get,
    'memory_search': memory_search,
    'memory_recent': memory_recent,
    'memory_pin': memory_pin,
    'memory_forget': memory_forget,
    'compact': compact,
    'log_event': log_event,
    'distill_run': distill_run,
    'list_events': list_events,
    'get_event': get_event,
    'query_failures': query_failures,
    'summarize_session': summarize_session,
    'secret_store': secret_store,
    'secret_get': secret_get,
    'secret_list': secret_list,
    'secret_delete': secret_delete,
    'secret_audit_log': secret_audit_log,
    'token_set': token_set,
    'token_status': token_status,
    'token_classify_error': token_classify_error,
    'session_timeline': session_timeline,
    'explain_failure': explain_failure,
    'compare_runs': compare_runs,
    'show_loaded_context': show_loaded_context,
    'healthcheck': healthcheck,
    'storage_status': storage_status,
    'export_snapshot': export_snapshot,
    'marketplace_list_service': marketplace_list_service,
    'marketplace_get_service': marketplace_get_service,
    'marketplace_list_services': marketplace_list_services,
    'marketplace_declare_policy': marketplace_declare_policy,
    'marketplace_get_policy': marketplace_get_policy,
    'marketplace_buy_service': marketplace_buy_service,
    'marketplace_list_transactions': marketplace_list_transactions,
    'marketplace_my_earnings': marketplace_my_earnings,
    'marketplace_settle_transaction': marketplace_settle_transaction,
}


def main():
    if len(sys.argv) < 3:
        print(_fail('Usage: nexus_service.py <method> <params_json>'))
        sys.exit(1)
    method = sys.argv[1]
    try:
        params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    except json.JSONDecodeError:
        print(_fail('Invalid JSON params'))
        sys.exit(1)

    if method not in METHOD_MAP:
        print(_fail(f'Unknown method: {method}'))
        sys.exit(1)

    try:
        result = METHOD_MAP[method](params)
        print(result)
    except Exception as e:
        print(_fail(str(e)))
        sys.exit(1)


if __name__ == '__main__':
    main()
