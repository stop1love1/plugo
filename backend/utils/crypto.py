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

# Legacy fixed salt — kept for backward compatibility with existing encrypted values
_LEGACY_SALT = b"plugo-fernet-key-v1"
_legacy_kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=_LEGACY_SALT, iterations=480_000)
_LEGACY_FERNET_KEY = base64.urlsafe_b64encode(_legacy_kdf.derive(_KEY.encode()))
_legacy_fernet = Fernet(_LEGACY_FERNET_KEY)

_SALT_SIZE = 16  # 16 bytes of random salt prepended to ciphertext


def _derive_fernet(salt: bytes) -> Fernet:
    """Derive a Fernet instance from SECRET_KEY and a given salt."""
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480_000)
    key = base64.urlsafe_b64encode(kdf.derive(_KEY.encode()))
    return Fernet(key)


def encrypt_value(value: str) -> str:
    """Encrypt a value using Fernet symmetric encryption with a random salt."""
    salt = os.urandom(_SALT_SIZE)
    fernet = _derive_fernet(salt)
    ciphertext = fernet.encrypt(value.encode())
    # Prepend the salt to the ciphertext so we can extract it on decryption
    combined = base64.urlsafe_b64encode(salt + base64.urlsafe_b64decode(ciphertext))
    return combined.decode()


def decrypt_value(encrypted: str) -> str:
    """Decrypt a Fernet-encrypted value. Supports both new (random salt) and legacy (fixed salt) formats."""
    try:
        # Try new format: extract random salt from first 16 bytes
        raw = base64.urlsafe_b64decode(encrypted.encode())
        salt = raw[:_SALT_SIZE]
        ciphertext = base64.urlsafe_b64encode(raw[_SALT_SIZE:])
        fernet = _derive_fernet(salt)
        return fernet.decrypt(ciphertext).decode()
    except Exception:
        pass
    try:
        # Fallback: try legacy fixed salt
        return _legacy_fernet.decrypt(encrypted.encode()).decode()
    except Exception:
        # Final fallback: return as-is for legacy plaintext values
        return encrypted
