import hashlib
import secrets

import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def generate_session_token() -> str:
    """Generate a cryptographically random 64-char hex session token."""
    return secrets.token_hex(32)


def generate_api_key() -> str:
    """Generate a random API key: 'labo_' prefix + 48 hex chars."""
    return "labo_" + secrets.token_hex(24)


def hash_api_key(key: str) -> str:
    """Hash an API key with SHA-256 for storage."""
    return hashlib.sha256(key.encode()).hexdigest()
