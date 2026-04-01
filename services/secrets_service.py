"""Secrets + auth support service for Context Nexus.

SecretsService: Production-grade AES-256-GCM encryption for secret storage.
AuthService: Auth state classification and token lifecycle support.
"""
import os
import base64
import hashlib
import hmac
import json
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
from storage.sqlite_adapter import SQLiteAdapter

_ENCRYPTION_KEY = os.environ.get(
    'CONTEXT_NEXUS_ENCRYPTION_KEY',
    base64.b64encode(b'context-nexus-local-dev-key-32bytes!!').decode()
)


def _derive_aes_key(key: str, purpose: bytes = b'nexus-secret-v1') -> bytes:
    """Derive a 32-byte key using HKDF-SHA256."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=purpose,
        backend=default_backend()
    )
    return hkdf.derive(key.encode())


def _derive_key_old(key: str, salt: bytes = b'nexus-seal-v1') -> bytes:
    """Derive a key using PBKDF2-HMAC-SHA256 (legacy)."""
    return hashlib.pbkdf2_hmac('sha256', key.encode(), salt, 100_000, dklen=32)


class SecretsService:
    """
    Production-grade secret storage using AES-256-GCM.
    Each secret gets a unique 12-byte nonce. Fail-closed on any decryption error.
    """

    def __init__(self, storage: SQLiteAdapter, encryption_key: str = None):
        self._s = storage
        raw = encryption_key or _ENCRYPTION_KEY
        self._key = _derive_aes_key(raw, b'nexus-secret-v1')
        self._aesgcm = AESGCM(self._key)

    def _encrypt(self, plaintext: str) -> str:
        """Encrypt with AES-256-GCM. Output: base64(nonce[12] + ciphertext + tag)."""
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode(), None)
        return base64.b64encode(nonce + ciphertext).decode()

    def _decrypt(self, ciphertext: str) -> Optional[str]:
        """Decrypt AES-256-GCM. Fail-closed on any error."""
        try:
            raw = base64.b64decode(ciphertext)
            nonce = raw[:12]
            ct = raw[12:]
            return self._aesgcm.decrypt(nonce, ct, None).decode()
        except Exception:
            return None  # Fail closed

    def store(self, name: str, value: str, metadata: dict = None, caller_id: str = None) -> bool:
        """Store an encrypted secret."""
        encrypted = self._encrypt(value)
        result = self._s.secret_store(name=name, encrypted_value=encrypted, metadata=metadata or {})
        self._s._audit_log_access('store', 'secret', name, caller_id=caller_id, success=result)
        return result

    def get(self, name: str, caller_id: str = None) -> Optional[str]:
        """Retrieve and decrypt a secret. Fail-closed on error."""
        row = self._s.secret_get(name=name)
        if not row:
            self._s._audit_log_access('get', 'secret', name, caller_id=caller_id, success=False, error='not_found')
            return None
        plaintext = self._decrypt(row.get('encrypted_value', ''))
        if plaintext is None:
            self._s._audit_log_access('get', 'secret', name, caller_id=caller_id, success=False, error='decrypt_failed')
            return None
        self._s._audit_log_access('get', 'secret', name, caller_id=caller_id, success=True)
        return plaintext

    def list_names(self) -> list:
        """List secret names and metadata only."""
        return self._s.secret_list_names()

    def delete(self, name: str, caller_id: str = None) -> bool:
        """Delete a secret."""
        result = self._s.secret_delete(name)
        self._s._audit_log_access('delete', 'secret', name, caller_id=caller_id, success=result)
        return result

    def rotate_metadata(self, name: str, metadata: dict) -> bool:
        """Update secret metadata without changing the value."""
        row = self._s.secret_get(name=name)
        if not row:
            return False
        return self._s.secret_store(name=name, encrypted_value=row.get('encrypted_value', ''), metadata=metadata)

    def validate_presence(self, required_secrets: list) -> dict:
        """Check which required secrets are present. Returns {name: present}."""
        stored = {r['name']: True for r in self._s.secret_list_names()}
        return {name: stored.get(name, False) for name in required_secrets}

    def is_usable(self, name: str) -> bool:
        """Check if a secret can be retrieved (decrypts correctly)."""
        plaintext = self.get(name)
        return plaintext is not None

    def rekey(self, old_key: str, new_key: str) -> dict:
        """Re-encrypt all secrets with a new encryption key. Returns {rekeyed, failed}."""
        old_service = SecretsService(self._s, old_key)
        new_service = SecretsService(self._s, new_key)
        secrets = self._s._secret_list_all()
        rekeyed = 0
        failed = 0
        for secret in secrets:
            try:
                plaintext = old_service._decrypt(secret['encrypted_value'])
                if plaintext is None:
                    failed += 1
                    continue
                new_encrypted = new_service._encrypt(plaintext)
                self._s._secret_update(secret['id'], new_encrypted)
                rekeyed += 1
            except Exception:
                failed += 1
        return {"rekeyed": rekeyed, "failed": failed}


class AuthService:
    """Auth state classification and token lifecycle support."""

    AUTH_FAILURE_CLASSES = {
        'missing_credential': 'No API key or token found in storage or environment.',
        'expired_token': 'Token has passed its expiry time and must be refreshed.',
        'refresh_failed': 'Refresh attempt returned an error. Token may be revoked.',
        'forbidden': 'API returned 403. Credentials are valid but lack permissions.',
        'invalid_token': 'Token rejected as malformed or with wrong signature.',
        'rate_limited': 'API returned 429. Back off and retry after cooldown.',
        'transport_error': 'Network-level failure. Check connectivity and DNS.',
        'unknown_auth_state': 'Unclassified auth failure. Check logs for details.',
    }

    def __init__(self, storage: SQLiteAdapter):
        self._s = storage

    def classify_error(self, error_code: str, error_message: str,
                       http_status: int = None) -> str:
        """Classify an auth error into a known failure type."""
        code = (error_code or '').lower()
        msg = (error_message or '').lower()
        status = http_status or 0

        if status == 401 or '401' in code or 'unauthorized' in msg:
            if 'expired' in msg or 'expir' in code:
                return 'expired_token'
            if 'refresh' in msg or 'refresh' in code:
                return 'refresh_failed'
            return 'invalid_token'
        if status == 403 or '403' in code or 'forbidden' in msg:
            return 'forbidden'
        if status == 429 or '429' in code or 'rate' in msg or 'too many' in msg:
            return 'rate_limited'
        if status == 0 or 'connection' in msg or 'timeout' in msg or 'network' in msg:
            return 'transport_error'
        if not error_code and not error_message:
            return 'missing_credential'
        return 'unknown_auth_state'

    def describe_error(self, error_class: str) -> str:
        """Human-readable description of an auth failure class."""
        return self.AUTH_FAILURE_CLASSES.get(
            error_class,
            self.AUTH_FAILURE_CLASSES['unknown_auth_state']
        )

    def token_set(self, provider: str, account_name: str,
                  access_token: str = None,
                  refresh_token: str = None,
                  access_expires_at: str = None,
                  refresh_expires_at: str = None,
                  metadata: dict = None) -> bool:
        """Store token credentials."""
        return self._s.token_set(
            provider=provider, account_name=account_name,
            access_token=access_token, refresh_token=refresh_token,
            access_expires_at=access_expires_at, refresh_expires_at=refresh_expires_at,
            metadata=metadata,
        )

    def token_get(self, provider: str, account_name: str) -> Optional[dict]:
        """Get token credentials."""
        return self._s.token_get(provider=provider, account_name=account_name)

    def token_is_expired(self, provider: str, account_name: str) -> bool:
        """Check if token is expired or about to expire."""
        return self._s.token_is_expired(provider=provider, account_name=account_name)

    def token_mark_expired(self, provider: str, account_name: str) -> bool:
        """Mark token as expired."""
        return self._s.token_mark_expired(provider=provider, account_name=account_name)

    def token_record_error(self, provider: str, account_name: str, error: str) -> bool:
        """Record an auth failure for a token."""
        return self._s.token_record_error(provider=provider, account_name=account_name, error=error)

    def token_status(self, provider: str, account_name: str) -> dict:
        """Get full token lifecycle status."""
        token = self._s.token_get(provider=provider, account_name=account_name)
        if not token:
            return {'status': 'missing', 'description': 'No token stored.'}
        is_exp = self._s.token_is_expired(provider=provider, account_name=account_name)
        return {
            'status': 'expired' if is_exp else token.get('status', 'unknown'),
            'provider': provider, 'account': account_name,
            'expires_at': token.get('access_expires_at'),
            'error_count': token.get('error_count', 0),
            'last_error': token.get('last_error'),
        }
