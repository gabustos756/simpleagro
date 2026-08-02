import hashlib
import os
from typing import Optional, Dict

SECRET_KEY = os.environ.get("SESSION_SECRET", "eduagro-secret-key-2026-cordoba")


def hash_password(password: str) -> str:
    """Hash password using SHA256 PBKDF2 with salt."""
    salt = b"eduagro_salt_2026"
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return pwd_hash.hex()


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify plain password against stored hash."""
    return hash_password(plain_password) == password_hash
