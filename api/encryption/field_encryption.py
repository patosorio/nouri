"""AES-256-GCM field encryption — docs/5_SECURITY_ARCH.md / docs/7_TECH_SPEC.md."""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from config import settings

_NONCE_LEN = 12


def _normalise_key(raw: bytes) -> bytes:
    """Accept raw 32-byte key or base64-encoded 32-byte key from env."""
    if len(raw) == 32:
        return raw
    try:
        decoded = base64.b64decode(raw, validate=True)
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass
    raise ValueError(
        "field_encryption_key must be 32 raw bytes or base64-encoded 32 bytes"
    )


class FieldEncryption:
    def __init__(self, key: bytes | None = None) -> None:
        self._aesgcm = AESGCM(_normalise_key(key if key is not None else settings.field_encryption_key))

    def encrypt(self, plaintext: str) -> bytes:
        nonce = os.urandom(_NONCE_LEN)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return nonce + ciphertext

    def decrypt(self, ciphertext: bytes) -> str:
        if len(ciphertext) <= _NONCE_LEN:
            raise ValueError("ciphertext too short")
        nonce = ciphertext[:_NONCE_LEN]
        payload = ciphertext[_NONCE_LEN:]
        plaintext = self._aesgcm.decrypt(nonce, payload, None)
        return plaintext.decode("utf-8")

    def encrypt_json(self, payload: str) -> str:
        """Encrypt to base64 string for JSONB storage."""
        return base64.b64encode(self.encrypt(payload)).decode("ascii")

    def decrypt_json(self, token: str) -> str:
        return self.decrypt(base64.b64decode(token.encode("ascii")))
