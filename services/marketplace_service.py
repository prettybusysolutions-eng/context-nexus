"""
Context Nexus Marketplace Service
v0.1 — Agent-to-agent service registry and policy engine
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from storage.sqlite_adapter import SQLiteAdapter


MARKETPLACE_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS marketplace_services (
        id TEXT PRIMARY KEY,
        slug TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        category TEXT NOT NULL,
        provider_agent_id TEXT NOT NULL,
        pricing_model TEXT NOT NULL,
        price_amount REAL NOT NULL,
        price_currency TEXT NOT NULL,
        split_table TEXT NOT NULL,
        trigger_signals TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        version TEXT NOT NULL DEFAULT '0.1.0',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS marketplace_buyer_policies (
        id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        policy_name TEXT NOT NULL,
        category TEXT NOT NULL,
        max_budget_amount REAL NOT NULL,
        budget_currency TEXT NOT NULL,
        budget_period TEXT NOT NULL,
        auto_approve_threshold REAL NOT NULL,
        trigger_signals TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS marketplace_transactions (
        id TEXT PRIMARY KEY,
        service_id TEXT NOT NULL,
        buyer_agent_id TEXT NOT NULL,
        amount REAL NOT NULL,
        currency TEXT NOT NULL,
        split_log TEXT NOT NULL,
        tx_hash TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS marketplace_pings (
        id TEXT PRIMARY KEY,
        service_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload TEXT NOT NULL,
        broadcast_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS marketplace_earnings (
        id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        role TEXT NOT NULL,
        service_id TEXT NOT NULL,
        gross_amount REAL NOT NULL,
        currency TEXT NOT NULL,
        net_amount REAL NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
]


def validate_split_table(split_table: dict) -> bool:
    """Split table must sum to 1.0 exactly."""
    if not isinstance(split_table, dict):
        return False
    total = sum(split_table.values())
    return abs(total - 1.0) < 0.0001


def validate_policy_threshold(threshold: float) -> bool:
    return 0.0 <= threshold <= 1.0


VALID_CATEGORIES = ['security', 'memory', 'code', 'data', 'ai', 'infra', 'compliance', 'monitoring']
VALID_CURRENCIES = ['USD', 'SOL', 'USDC', 'CREDIT']
VALID_PRICING_MODELS = ['per_call', 'per_hour', 'per_day', 'per_month', 'flat']
VALID_BUDGET_PERIODS = ['per_hour', 'per_day', 'per_month', 'lifetime']
VALID_STATUSES = ['active', 'paused', 'deprecated', 'pending', 'settled', 'failed', 'refunded']
VALID_EVENT_TYPES = ['listed', 'updated', 'price_change', 'deprecated']


class MarketplaceService:
    def __init__(self, db: SQLiteAdapter):
        self.db = db
        self._ensure_tables()

    def _ensure_tables(self):
        for sql in MARKETPLACE_TABLES:
            self.db.execute(sql)

    # ── Service Registry ────────────────────────────────────────────────

    def list_service(self, slug: str, name: str, description: str, category: str,
                     pricing_model: str, price_amount: float, price_currency: str,
                     split_table: dict, trigger_signals: list, provider_agent_id: str,
                     version: str = '0.1.0') -> dict:
        if category not in VALID_CATEGORIES:
            return {'ok': False, 'error': f'invalid_category: must be one of {VALID_CATEGORIES}'}
        if pricing_model not in VALID_PRICING_MODELS:
            return {'ok': False, 'error': f'invalid_pricing_model: must be one of {VALID_PRICING_MODELS}'}
        if price_currency not in VALID_CURRENCIES:
            return {'ok': False, 'error': f'invalid_currency: must be one of {VALID_CURRENCIES}'}
        if not validate_split_table(split_table):
            return {'ok': False, 'error': 'invalid_split_table: must sum to 1.0'}
        if not isinstance(trigger_signals, list) or not trigger_signals:
            return {'ok': False, 'error': 'trigger_signals must be a non-empty list'}

        now = datetime.now(timezone.utc).isoformat()
        service_id = str(uuid.uuid4())

        try:
            self.db.execute("""
                INSERT INTO marketplace_services 
                (id, slug, name, description, category, provider_agent_id, pricing_model,
                 price_amount, price_currency, split_table, trigger_signals, status, version,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """, [service_id, slug, name, description, category, provider_agent_id,
                  pricing_model, price_amount, price_currency, json.dumps(split_table),
                  json.dumps(trigger_signals), version, now, now])
        except Exception as e:
            if 'UNIQUE constraint' in str(e):
                return {'ok': False, 'error': f'service_slug_already_exists: {slug}'}
            return {'ok': False, 'error': str(e)}

        # Broadcast ping
        self._broadcast_ping(service_id, 'listed', {
            'slug': slug, 'name': name, 'category': category,
            'price_amount': price_amount, 'price_currency': price_currency,
            'trigger_signals': trigger_signals
        })

        return {'ok': True, 'service_id': service_id, 'slug': slug}

    def get_service(self, service_id: str = None, slug: str = None) -> dict:
        if service_id:
            row = self.db.execute(
                "SELECT * FROM marketplace_services WHERE id = ?", [service_id]).fetchone()
        elif slug:
            row = self.db.execute(
                "SELECT * FROM marketplace_services WHERE slug = ?", [slug]).fetchone()
        else:
            return {'ok': False, 'error': 'service_id or slug required'}

        if not row:
            return {'ok': False, 'error': 'service_not_found'}
        return {'ok': True, 'service': dict(row)}

    def list_services(self, category: str = None, status: str = 'active',
                      limit: int = 50) -> dict:
        query = "SELECT * FROM marketplace_services WHERE 1=1"
        params = []
        if category:
            query += " AND category = ?"
            params.append(category)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self.db.execute(query, params).fetchall()
        return {
            'ok': True,
            'count': len(rows),
            'services': [dict(r) for r in rows]
        }

    def update_service_status(self, service_id: str, status: str) -> dict:
        if status not in ['active', 'paused', 'deprecated']:
            return {'ok': False, 'error': f'invalid_status: must be one of active/paused/deprecated'}
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "UPDATE marketplace_services SET status = ?, updated_at = ? WHERE id = ?",
            [status, now, service_id])
        self._broadcast_ping(service_id, status, {'status': status})
        return {'ok': True, 'service_id': service_id, 'status': status}

    # ── Buyer Policies ──────────────────────────────────────────────────

    def declare_policy(self, policy_name: str, category: str, max_budget_amount: float,
                       budget_currency: str, budget_period: str, auto_approve_threshold: float,
                       trigger_signals: list, agent_id: str) -> dict:
        if category not in VALID_CATEGORIES:
            return {'ok': False, 'error': f'invalid_category: must be one of {VALID_CATEGORIES}'}
        if budget_currency not in VALID_CURRENCIES:
            return {'ok': False, 'error': f'invalid_currency: must be one of {VALID_CURRENCIES}'}
        if budget_period not in VALID_BUDGET_PERIODS:
            return {'ok': False, 'error': f'invalid_budget_period: must be one of {VALID_BUDGET_PERIODS}'}
        if not validate_policy_threshold(auto_approve_threshold):
            return {'ok': False, 'error': 'auto_approve_threshold must be 0.0-1.0'}
        if not isinstance(trigger_signals, list):
            return {'ok': False, 'error': 'trigger_signals must be a list'}

        now = datetime.now(timezone.utc).isoformat()
        policy_id = str(uuid.uuid4())

        self.db.execute("""
            INSERT INTO marketplace_buyer_policies
            (id, agent_id, policy_name, category, max_budget_amount, budget_currency,
             budget_period, auto_approve_threshold, trigger_signals, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
        """, [policy_id, agent_id, policy_name, category, max_budget_amount, budget_currency,
              budget_period, auto_approve_threshold, json.dumps(trigger_signals), now])
        return {'ok': True, 'policy_id': policy_id}

    def get_policy(self, agent_id: str) -> dict:
        rows = self.db.execute(
            "SELECT * FROM marketplace_buyer_policies WHERE agent_id = ? AND status = 'active'",
            [agent_id]).fetchall()
        return {'ok': True, 'policies': [dict(r) for r in rows]}

    def get_current_spend(self, agent_id: str, policy: dict) -> float:
        period = policy['budget_period']
        now = datetime.now(timezone.utc)

        if period == 'per_hour':
            since = now.replace(minute=0, second=0, microsecond=0).isoformat()
        elif period == 'per_day':
            since = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        elif period == 'per_month':
            since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        else:
            since = '1970-01-01T00:00:00+00:00'

        rows = self.db.execute("""
            SELECT SUM(amount) as total FROM marketplace_transactions
            WHERE buyer_agent_id = ? AND status = 'settled' AND created_at >= ?
        """, [agent_id, since]).fetchone()
        return rows['total'] or 0.0

    # ── Purchase Engine ─────────────────────────────────────────────────

    def evaluate_and_purchase(self, service_id: str, buyer_agent_id: str,
                              budget_agent_id: str) -> dict:
        service_row = self.db.execute(
            "SELECT * FROM marketplace_services WHERE id = ?", [service_id]).fetchone()
        if not service_row:
            return {'action': 'error', 'reason': 'service_not_found'}
        service = dict(service_row)

        if service['status'] != 'active':
            return {'action': 'ignore', 'reason': f'service_status={service["status"]}'}

        policies = self.db.execute(
            "SELECT * FROM marketplace_buyer_policies WHERE agent_id = ? AND status = 'active'",
            [buyer_agent_id]).fetchall()

        best_action = {'action': 'no_matching_policy'}
        best_score = -1

        for policy_row in policies:
            policy = dict(policy_row)
            trigger_list = json.loads(policy['trigger_signals'])
            service_triggers = json.loads(service['trigger_signals'])

            # Signal match
            signal_match = any(s in trigger_list for s in service_triggers)
            if not signal_match:
                continue

            # Budget check
            current_spend = self.get_current_spend(buyer_agent_id, policy)
            remaining = policy['max_budget_amount'] - current_spend
            if remaining <= 0:
                best_action = {'action': 'reject', 'reason': 'budget_exhausted', 'policy_id': policy['id']}
                continue

            price = service['price_amount']
            if price > remaining:
                best_action = {'action': 'reject', 'reason': 'price_exceeds_budget',
                               'price': price, 'remaining': remaining}
                continue

            # Calculate approval score
            score = self._calculate_approval_score(service, policy)
            if score >= policy['auto_approve_threshold']:
                # Auto-approve: execute purchase
                return self._execute_purchase(service, buyer_agent_id, budget_agent_id, policy)
            elif score > best_score:
                best_score = score
                best_action = {'action': 'flag_for_review', 'score': score,
                               'service_id': service_id, 'policy_id': policy['id']}

        return best_action

    def _calculate_approval_score(self, service: dict, policy: dict) -> float:
        score = 0.0
        signals = json.loads(service['trigger_signals'])
        policy_signals = json.loads(policy['trigger_signals'])

        # Signal overlap (40% weight)
        overlap = len(set(signals) & set(policy_signals))
        total = len(set(signals) | set(policy_signals))
        if total > 0:
            signal_score = overlap / total
        else:
            signal_score = 0.0
        score += signal_score * 0.4

        # Budget fit (30% weight) — closer to budget limit = better fit
        price = service['price_amount']
        budget = policy['max_budget_amount']
        budget_fit = min(price / budget, 1.0) if budget > 0 else 0.0
        score += budget_fit * 0.3

        # Category match (30% weight)
        category_match = 1.0 if service['category'] == policy['category'] else 0.0
        score += category_match * 0.3

        return min(score, 1.0)

    def _execute_purchase(self, service: dict, buyer_agent_id: str,
                          budget_agent_id: str, policy: dict) -> dict:
        tx_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        amount = service['price_amount']
        currency = service['price_currency']
        split_table = json.loads(service['split_table'])

        # Record transaction as pending (off-chain for v0.1)
        self.db.execute("""
            INSERT INTO marketplace_transactions
            (id, service_id, buyer_agent_id, amount, currency, split_log, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
        """, [tx_id, service['id'], buyer_agent_id, amount, currency,
              json.dumps(split_table), now])

        # Record earnings for each split recipient (off-chain ledger)
        for role, percentage in split_table.items():
            self.db.execute("""
                INSERT INTO marketplace_earnings
                (id, agent_id, role, service_id, gross_amount, currency, net_amount, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [str(uuid.uuid4()), service['provider_agent_id'], role, service['id'],
                  amount, currency, amount * percentage, now])

        return {
            'action': 'purchased',
            'transaction_id': tx_id,
            'service_id': service['id'],
            'service_slug': service['slug'],
            'amount': amount,
            'currency': currency,
            'split_log': {k: round(v * amount, 4) for k, v in split_table.items()},
            'status': 'pending_settlement'
        }

    def buy_service(self, service_id: str, buyer_agent_id: str, budget_agent_id: str) -> dict:
        return self.evaluate_and_purchase(service_id, buyer_agent_id, budget_agent_id)

    # ── Transactions & Earnings ────────────────────────────────────────

    def list_transactions(self, status: str = None, limit: int = 50) -> dict:
        query = "SELECT * FROM marketplace_transactions WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self.db.execute(query, params).fetchall()
        return {
            'ok': True,
            'count': len(rows),
            'transactions': [dict(r) for r in rows]
        }

    def my_earnings(self, agent_id: str, currency: str = 'USD',
                    period: str = 'per_month') -> dict:
        now = datetime.now(timezone.utc)
        if period == 'per_hour':
            since = now.replace(minute=0, second=0, microsecond=0).isoformat()
        elif period == 'per_day':
            since = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        elif period == 'per_month':
            since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        else:
            since = '1970-01-01T00:00:00+00:00'

        rows = self.db.execute("""
            SELECT role, SUM(net_amount) as total, COUNT(*) as tx_count
            FROM marketplace_earnings
            WHERE agent_id = ? AND currency = ? AND created_at >= ?
            GROUP BY role
        """, [agent_id, currency, since]).fetchall()

        total = sum(r['total'] for r in rows)
        return {
            'ok': True,
            'agent_id': agent_id,
            'currency': currency,
            'period': period,
            'since': since,
            'total_earnings': round(total, 4),
            'by_role': [dict(r) for r in rows],
            'transaction_count': sum(r['tx_count'] for r in rows)
        }

    def settle_transaction(self, transaction_id: str, tx_hash: str) -> dict:
        self.db.execute(
            "UPDATE marketplace_transactions SET status = 'settled', tx_hash = ? WHERE id = ?",
            [tx_hash, transaction_id])
        return {'ok': True, 'transaction_id': transaction_id, 'status': 'settled'}

    # ── Ping / Event Broadcast ──────────────────────────────────────────

    def _broadcast_ping(self, service_id: str, event_type: str, payload: dict):
        ping_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute("""
            INSERT INTO marketplace_pings (id, service_id, event_type, payload, broadcast_at)
            VALUES (?, ?, ?, ?, ?)
        """, [ping_id, service_id, event_type, json.dumps(payload), now])

    def get_ping_history(self, service_id: str = None, limit: int = 20) -> dict:
        query = "SELECT * FROM marketplace_pings WHERE 1=1"
        params = []
        if service_id:
            query += " AND service_id = ?"
            params.append(service_id)
        query += " ORDER BY broadcast_at DESC LIMIT ?"
        params.append(limit)
        rows = self.db.execute(query, params).fetchall()
        return {
            'ok': True,
            'pings': [dict(r) for r in rows]
        }
