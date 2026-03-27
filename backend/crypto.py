"""
Encryption utilities for sensitive data (API keys, auth tokens).

Uses Fernet symmetric encryption with the app's SECRET_KEY.
Encrypted values are stored as base64 strings in the database.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from config import settings


def _get_fernet() -> Fernet:
    """Derive a Fernet key from the app's secret key."""
    # Fernet requires a 32-byte base64-encoded key
    # Derive it deterministically from SECRET_KEY
    key_bytes = hashlib.sha256(settings.secret_key.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt(plaintext: str) -> str:
    """Encrypt a string. Returns base64-encoded ciphertext."""
    if not plaintext:
        return ""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext. Returns plaintext string."""
    if not ciphertext:
        return ""
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        # If decryption fails (e.g., key changed), return empty string
        # Log this in production
        return ""
