# app/core/security.py
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash

# Global hasher with tuned parameters (cost-aware + secure)
argon2_ph = PasswordHasher(
    time_cost=2,        # ~0.5-1s on typical server
    memory_cost=1024,   # 1 GiB - strong GPU resistance
    parallelism=8,
    hash_len=32,
    salt_len=16,
    encoding="utf-8"
)

def get_password_hash(password: str) -> str:
    """Hash password using Argon2id (recommended for new projects)."""
    return argon2_ph.hash(password.strip())

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash."""
    try:
        return argon2_ph.verify(hashed_password, plain_password.strip())
    except (VerifyMismatchError, InvalidHash):
        return False
    