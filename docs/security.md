# Context Nexus — Security

## Secrets Encryption

### Algorithm
Rolled XOR with PBKDF2-derived key material:

1. `encryption_key` from env → PBKDF2 (100,000 iterations, SHA256) → 32-byte key
2. Separate PBKDF2 derivation → 32-byte HMAC key
3. Value encrypted with XOR + HMAC-SHA256 tag
4. Stored: `iv || ciphertext || hmac_tag`

### Key Derivation
```python
def derive_keys(master_key: str) -> tuple[bytes, bytes]:
    enc_key = PBKDF2(master_key, b'encryption', 100000, dkLen=32, hashlib.sha256)
    mac_key = PBKDF2(master_key, b'mac', 100000, dkLen=32, hashlib.sha256)
    return enc_key, mac_key
```

### Fail-Closed Decryption
```python
def decrypt(ciphertext: str) -> str | None:
    try:
        iv, ct, tag = parse_ciphertext(ciphertext)
        dec = xor_bytes(iv, ct)
        if not hmac_verify(tag, ct, mac_key):
            return None  # fail-closed: wrong key or tampered
        return dec.decode()
    except Exception:
        return None  # any error → empty
```

If decryption fails for any reason (wrong key, tampered data, corruption), the function returns `None`. No error message, no stack trace, no partial plaintext.

---

## Redaction

### Automatic Redaction Patterns
The logging service redacts before storage:

```python
REDACTION_PATTERNS = [
    (r'sk_live_[A-Za-z0-9]{24,}', '[STRIPE_KEY]'),
    (r'sk_test_[A-Za-z0-9]{24,}', '[STRIPE_KEY]'),
    (r'ghp_[A-Za-z0-9]{36}', '[GITHUB_TOKEN]'),
    (r'gho_[A-Za-z0-9]{36}', '[GITHUB_TOKEN]'),
    (r'Bearer [A-Za-z0-9\-._~+/]+', '[BEARER_TOKEN]'),
    (r'-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----', '[PRIVATE_KEY]'),
    (r'eyJ[A-Za-z0-9\-_]+\.eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+', '[JWT]'),
    (r'AIza[A-Za-z0-9\-_]{35}', '[GOOGLE_API_KEY]'),
]
```

### Redacted Fields
- Tool call arguments
- Error messages containing tokens
- Session metadata with credentials
- `secrets.value` is NEVER logged (stored encrypted, never in events)

---

## Auth Failure Classification

### 8 Failure Types

| Type | Trigger | Recovery Action |
|------|---------|----------------|
| `missing_credential` | Key not in secrets or env | `nexus_secrets store name=...` |
| `expired_token` | `expires_at` < now | `nexus_secrets rotate name=...` |
| `refresh_failed` | Refresh attempt returned error | Check network, retry with new token |
| `forbidden` | HTTP 403 | Check permissions, scopes |
| `invalid_token` | HTTP 401 but not expired | Re-authenticate |
| `rate_limited` | HTTP 429 | Wait and retry with backoff |
| `transport_error` | Network/connectivity failure | Check firewall, DNS |
| `unknown_auth_state` | Unclassified | Manual investigation |

### Token Registry
Tracks OAuth lifecycle:
```sql
CREATE TABLE token_registry (
    provider TEXT PRIMARY KEY,
    access_token TEXT,
    refresh_token TEXT,
    expires_at TEXT,
    scope TEXT,
    metadata TEXT,
    updated_at TEXT NOT NULL
);
```

---

## Access Control

### Scope Isolation
- Memories are scoped: `ephemeral`, `durable`, `pinned`
- Sessions can only read memories in their authorized scopes
- Tool calls enforce scope boundaries

### No Cross-Tenant Access
- SQLite: file permissions are the boundary
- PostgreSQL (future): row-level security via schema

---

## Secure Defaults

1. **Fail-closed**: decryption errors return empty, never plaintext
2. **No secret values in logs**: automatic redaction on all event logging
3. **No credentials in memory**: secrets stored encrypted, not in memory fields
4. **No error disclosure**: auth errors classified but not detailed in responses
5. **Compaction respects pinned**: pinned memories never auto-deleted

---

## Security Checklist for Production

- [ ] Set `CONTEXT_NEXUS_ENCRYPTION_KEY` to a strong random value
- [ ] Move SQLite file to encrypted volume (FileVault on macOS)
- [ ] Restrict `~/.openclaw/context-nexus/` to owner-only: `chmod 700`
- [ ] For PostgreSQL: use TLS connection + minimal-privilege DB user
- [ ] Rotate encryption key periodically: `nexus_admin action=rotate_key`
- [ ] Audit secret access: `nexus_secrets action=list` + review metadata
- [ ] Enable firewall on PostgreSQL if exposed to network
