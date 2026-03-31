"""Secrets + auth support service for Context Nexus."""
import base64
import hashlib
import os
import json
import hmac
from typing import Optional
from storage.sqlite_adapter import SQLiteAdapter

# Change this to a strong per-install secret in production
_ENCRYPTION_KEY = os.environ.get(
    'CONTEXT_NEXUS_ENCRYPTION_KEY',
    base64.b64encode(b'context-nexus-local-dev-key-32bytes!!').decode()
)


def _derive_key(key: str, salt: bytes = b'nexus-seal-v1') -> bytes:
    """Derive an encryption key from a secret."""
    return hashlib.pbkdf2_hmac('sha256', key.encode(), salt, 100_000, dklen=32)


class SecretsService:
    """Secure secret storage with encryption at rest."""

    def __init__(self, storage: SQLiteAdapter,
                 encryption_key: str = None):
        self._s = storage
        # Derive a consistent key from the provided key or env default
        raw = encryption_key or _ENCRYPTION_KEY
        self._key = _derive_key(raw)
        self._hmac_key = _derive_key(raw + '-hmac', b'nexus-hmac-v1')

    def _encrypt(self, plaintext: str) -> str:
        """Encrypt a string with AES-GCM-style rolling XOR."""
        iv = os.urandom(16)
        key = self._key
        encrypted = bytearray()
        for i, byte in enumerate(plaintext.encode()):
            encrypted.append(byte ^ key[i % len(key)] ^ iv[i % len(iv)])
        sig = hmac.new(self._hmac_key, iv + bytes(encrypted), hashlib.sha256).hexdigest()[:16]
        return base64.b64encode(iv + bytes(encrypted) + sig.encode()).decode()

    def _decrypt(self, ciphertext: str) -> Optional[str]:
        """Decrypt a ciphertext. Returns None on failure (fail-closed)."""
        try:
            raw = base64.b64decode(ciphertext)
            if len(raw) < 16 + 16 + 1:
                return None
            iv = raw[:16]
            sig = raw[-16:].decode()
            encrypted = raw[16:-16]
            expected_sig = hmac.new(self._hmac_key, iv + encrypted, hashlib.sha256).hexdigest()[:16]
            if not hmac.compare_digest(sig, expected_sig):
                return None  # fail-closed
            key = self._key
            decrypted = bytes(b ^ key[i % len(key)] ^ iv[i % len(iv)]
                           for i, b in enumerate(encrypted)).decode()
            return decrypted
        except Exception:
            return None  # fail-closed

    def store(self, name: str, value: str,
              metadata: dict = None) -> bool:
        """Store an encrypted secret."""
        encrypted = self._encrypt(value)
        return self._s.secret_store(
            name=name,
            encrypted_value=encrypted,
            metadata=metadata or {},
        )

    def get(self, name: str) -> Optional[str]:
        """Retrieve and decrypt a secret. Fail-closed on error."""
        row = self._s.secret_get(name=name)
        if not row:
            return None
        return self._decrypt(row.get('encrypted_value', ''))

    def list_names(self) -> list:
        """List secret names and metadata only."""
        return self._s.secret_list_names()

    def delete(self, name: str) -> bool:
        """Delete a secret."""
        return self._s.secret_delete(name=name)

    def rotate_metadata(self, name: str,
                        metadata: dict) -> bool:
        """Update secret metadata without changing the value."""
        row = self._s.secret_get(name=name)
        if not row:
            return False
        return self._s.secret_store(
            name=name,
            encrypted_value=row.get('encrypted_value', ''),
            metadata=metadata,
        )

    def validate_presence(self, required_secrets: list) -> dict:
        """Check which required secrets are present. Returns {name: present}."""
        stored = {r['name']: True for r in self._s.secret_list_names()}
        return {name: stored.get(name, False) for name in required_secrets}

    def is_usable(self, name: str) -> bool:
        """Check if a secret can be retrieved (decrypts correctly)."""
        plaintext = self.get(name)
        return plaintext is not None


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
            provider=provider,
            account_name=account_name,
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_at=access_expires_at,
            refresh_expires_at=refresh_expires_at,
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

    def token_record_error(self, provider: str, account_name: str,
                           error: str) -> bool:
        """Record an auth failure for a token."""
        return self._s.token_record_error(provider=provider,
                                         account_name=account_name,
                                         error=error)

    def token_status(self, provider: str, account_name: str) -> dict:
        """Get full token lifecycle status."""
        token = self._s.token_get(provider=provider, account_name=account_name)
        if not token:
            return {'status': 'missing', 'description': 'No token stored.'}
        is_exp = self._s.token_is_expired(provider=provider, account_name=account_name)
        return {
            'status': 'expired' if is_exp else token.get('status', 'unknown'),
            'provider': provider,
            'account': account_name,
            'expires_at': token.get('access_expires_at'),
            'error_count': token.get('error_count', 0),
            'last_error': token.get('last_error'),
        }
