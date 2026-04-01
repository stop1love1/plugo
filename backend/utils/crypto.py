import base64
import os
import warnings

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Use SECRET_KEY from env as encryption key
_KEY = os.getenv("SECRET_KEY")
if not _KEY or _KEY == "default-key-change-me":
    warnings.warn(
        "SECRET_KEY is not set or using default value! Encryption is NOT secure.",
        stacklevel=2,
    )
    _KEY = "default-key-change-me"  # Still allow dev to work but warn loudly
# Derive a Fernet-compatible key from SECRET_KEY using PBKDF2
_SALT = b"plugo-fernet-key-v1"  # Fixed salt — key changes when SECRET_KEY changes
_kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=_SALT, iterations=480_000)
_FERNET_KEY = base64.urlsafe_b64encode(_kdf.derive(_KEY.encode()))
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
