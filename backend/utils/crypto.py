import base64
import os
import warnings
from hashlib import sha256

from cryptography.fernet import Fernet

# Use SECRET_KEY from env as encryption key
_KEY = os.getenv("SECRET_KEY")
if not _KEY or _KEY == "default-key-change-me":
    warnings.warn(
        "SECRET_KEY is not set or using default value! Encryption is NOT secure.",
        stacklevel=2,
    )
    _KEY = "default-key-change-me"  # Still allow dev to work but warn loudly
# Derive a Fernet-compatible key from SECRET_KEY
_FERNET_KEY = base64.urlsafe_b64encode(sha256(_KEY.encode()).digest())
_fernet = Fernet(_FERNET_KEY)


def encrypt_value(value: str) -> str:
    """Encrypt a value using Fernet symmetric encryption."""
    return _fernet.encrypt(value.encode()).decode()


def decrypt_value(encrypted: str) -> str:
    """Decrypt a Fernet-encrypted value."""
    try:
        return _fernet.decrypt(encrypted.encode()).decode()
    except Exception:
        # Fallback: return as-is for legacy plaintext values
        return encrypted
