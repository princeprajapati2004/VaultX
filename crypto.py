"""Encryption helpers for VaultX."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from constants import ITERATIONS


def generate_key(password: str, salt: str) -> bytes:
    """Derive the Fernet key from a password and salt."""

    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        bytes.fromhex(salt),
        ITERATIONS,
        dklen=32,
    )

    return base64.urlsafe_b64encode(key)


def encrypt_bytes(data: bytes, password: str, salt: str) -> bytes:
    """Encrypt bytes with a password-derived Fernet key."""

    cipher = Fernet(generate_key(password, salt))
    return cipher.encrypt(data)


def decrypt_bytes(data: bytes, password: str, salt: str) -> bytes:
    """Decrypt bytes with a password-derived Fernet key."""

    cipher = Fernet(generate_key(password, salt))
    return cipher.decrypt(data)