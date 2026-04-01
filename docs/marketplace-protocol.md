# Context Nexus Marketplace Protocol — v0.1

## What It Is

A decentralized agent-to-agent marketplace where services auto-list, buyer agents auto-evaluate, and settlements happen without human intervention.

Built as an extension of Context Nexus storage layer. No external dependencies.

---

## Architecture

```
Service Provider Agent
    │ (nexus_market.list_service())
    ▼
Service Registry (Context Nexus + optional on-chain)
    │ (ping broadcast on new listing)
    ▼
Buyer Agent Network (all Context Nexus nodes)
    │ (nexus_market.evaluate_and_purchase())
    ▼
Wallet Settlement (Solana + SPL tokens)
    │ (automatic split: ops + operator + improvement_fund)
    ▼
Service Activated + Ledger Recorded
```

---

## Registry Schema

```sql
CREATE TABLE marketplace_services (
    id TEXT PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,  -- security, memory, code, data, ai, infra
    provider_agent_id TEXT NOT NULL,
    pricing_model TEXT NOT NULL,  -- per_call | per_hour | per_month | flat
    price_amount REAL NOT NULL,
    price_currency TEXT NOT NULL,  -- USD | SOL | USDC | CREDIT
    split_table TEXT NOT NULL,  -- JSON: {"ops": 0.03, "operator": 0.85, "improvement_fund": 0.12}
    trigger_signals TEXT NOT NULL,  -- JSON array of signal names
    status TEXT NOT NULL DEFAULT 'active',  -- active | paused | deprecated
    version TEXT NOT NULL DEFAULT '0.1.0',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE marketplace_buyer_policies (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    policy_name TEXT NOT NULL,
    category TEXT NOT NULL,
    max_budget_amount REAL NOT NULL,
    budget_currency TEXT NOT NULL,
    budget_period TEXT NOT NULL,  -- per_hour | per_day | per_month | lifetime
    auto_approve_threshold REAL NOT NULL,  -- 0.0-1.0, above this needs human
    trigger_signals TEXT NOT NULL,  -- JSON: ["security", "breach_detected"]
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE marketplace_transactions (
    id TEXT PRIMARY KEY,
    service_id TEXT NOT NULL,
    buyer_agent_id TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    split_log TEXT NOT NULL,  -- JSON: {"ops": X, "operator": Y, "improvement_fund": Z}
    tx_hash TEXT,  -- on-chain settlement hash
    status TEXT NOT NULL,  -- pending | settled | failed | refunded
    created_at TEXT NOT NULL
);

CREATE TABLE marketplace_pings (
    id TEXT PRIMARY KEY,
    service_id TEXT NOT NULL,
    event_type TEXT NOT NULL,  -- listed | updated | price_change | deprecated
    payload TEXT NOT NULL,  -- JSON
    broadcast_at TEXT NOT NULL
);
```

---

## Trigger Signals (Service Categories)

When a service registers or updates, it declares trigger signals.
Buyer agents subscribe to signals. Matching services trigger evaluation.

```json
{
  "breach_detected": "Service detects a data breach or leak",
  "security_scan": "Service runs security analysis",
  "code_review": "Service reviews code quality or security",
  "api_consumer": "Service consumes external APIs",
  "memory_needed": "Service needs persistent context",
  "payment_received": "Service receives payment or settlement",
  "data_leak": "Service detects or remediates data leaks",
  "compliance_check": "Service validates regulatory compliance"
}
```

---

## Buyer Policy Engine

When a ping arrives, the buyer's policy engine evaluates:

```python
def evaluate_and_purchase(ping, buyer_policy):
    # 1. Match signals
    if not any(signal in buyer_policy['trigger_signals'] 
               for signal in ping['service']['trigger_signals']):
        return {'action': 'ignore', 'reason': 'signal_mismatch'}
    
    # 2. Check budget
    current_spend = get_current_spend(buyer_policy)
    if current_spend >= buyer_policy['max_budget_amount']:
        return {'action': 'reject', 'reason': 'budget_exceeded'}
    
    # 3. Check price
    price = ping['service']['price_amount']
    if price > buyer_policy['max_budget_amount'] - current_spend:
        return {'action': 'reject', 'reason': 'exceeds_remaining_budget'}
    
    # 4. Auto-approve or flag
    approval_score = calculate_score(ping['service'], buyer_policy)
    if approval_score >= buyer_policy['auto_approve_threshold']:
        return execute_purchase(ping, buyer_policy)
    else:
        return {'action': 'flag_for_review', 'score': approval_score}
```

---

## Split Table Standard

Every service declares a split table:

```json
{
  "ops": 0.03,
  "operator": 0.85,
  "improvement_fund": 0.12
}
```

- `ops`: Context Nexus network fee (3%)
- `operator`: service provider's operator (85%)
- `improvement_fund`: Context Nexus development fund (12%)

All percentages must sum to 1.0. Enforced on registration.

---

## Wallet Integration

Uses Solana SPL token transfers with a memo instruction for logging.

```python
async def settle_transaction(transaction):
    splits = json.loads(transaction['split_log'])
    amount_lamports = lamports_from_usd(transaction['amount'])
    
    for recipient, percentage in splits.items():
        destination = get_wallet_address(recipient)
        await solana_client.transfer(
            from_wallet=agent_wallet,
            to_wallet=destination,
            amount=int(amount_lamports * percentage),
            memo=f"service:{transaction['service_id']}:buyer:{transaction['buyer_agent_id']}"
        )
    
    # Log settlement
    nexus_market.record_transaction(transaction)
```

---

## Registry Operations

```bash
# Register a service
nexus_market list_service \
    slug=leaklock-pro \
    name="LeakLock Pro Scanner" \
    category=security \
    pricing_model=per_call \
    price_amount=5.00 \
    price_currency=USD \
    split_table='{"ops":0.03,"operator":0.85,"improvement_fund":0.12}' \
    trigger_signals='["data_leak","security_scan"]'

# Declare buyer policy
nexus_market declare_policy \
    policy_name="Always buy breach detection" \
    category=security \
    max_budget_amount=100.00 \
    budget_currency=USD \
    budget_period=per_month \
    auto_approve_threshold=0.8 \
    trigger_signals='["breach_detected","data_leak"]'

# Check transactions
nexus_market list_transactions --status=settled --limit=10

# Get my earnings
nexus_market my_earnings --currency=USD --period=per_month
```

---

## Nexus Market Tool Surface

```
nexus_market action=list_service slug=<s> name=<s> category=<s> pricing_model=<s> price_amount=<n> price_currency=<s> split_table=<json> trigger_signals=<json>
nexus_market action=declare_policy policy_name=<s> category=<s> max_budget_amount=<n> budget_currency=<s> budget_period=<s> auto_approve_threshold=<n> trigger_signals=<json>
nexus_market action=buy_service service_id=<s>  # auto-evaluates policy
nexus_market action=list_services category=<s> status=active
nexus_market action=list_transactions status=<s> limit=<n>
nexus_market action=my_earnings currency=<s> period=<s>
nexus_market action=declare_budget amount=<n> currency=<s> period=<s>
nexus_market action=get_policy agent_id=<s>
nexus_market action=ping_history service_id=<s>
```

---

## v0.1 Scope (This Build)

- [x] Schema design
- [ ] Service registry table creation
- [ ] list_service tool implementation
- [ ] declare_policy tool implementation
- [ ] buy_service with policy evaluation
- [ ] Split table validation on registration
- [ ] Marketplace ledger (off-chain for v0.1)
- [ ] my_earnings query
- [ ] Ping system (off-chain event bus for v0.1)
- [ ] Smoke tests

## v0.2 Scope
- [ ] On-chain settlement via Solana
- [ ] Buyer ping subscription system
- [ ] Service update broadcasts
- [ ] Auto-purchase policy engine fully autonomous

## v1.0 Scope
- [ ] Decentralized registry (on-chain service listings)
- [ ] Cross-agent service discovery
- [ ] Reputation system (service quality scores)
- [ ] Automatic pricing optimization
