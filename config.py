"""Configuration and password storage helpers for VaultX."""

from __future__ import annotations

import hashlib
import json
import secrets

from constants import CONFIG_FILE, DATA_DIR, ITERATIONS, LOG_DIR, VAULT_DIR


def derive_key(password: str, salt: str) -> str:
    """Derive a password hash from the given password and salt."""

    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        bytes.fromhex(salt),
        ITERATIONS,
    ).hex()


def save_new_password(password: str) -> None:
    """Create the initial configuration file for a new vault."""

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    VAULT_DIR.mkdir(parents=True, exist_ok=True)

    salt = secrets.token_hex(16)
    password_hash = derive_key(password, salt)

    config = {
        "version": 1,
        "iterations": ITERATIONS,
        "salt": salt,
        "password_hash": password_hash,
    }

    with CONFIG_FILE.open("w", encoding="utf-8") as file_handle:
        json.dump(config, file_handle, indent=4)


def get_salt() -> str:
    """Load the stored salt from the configuration file."""

    with CONFIG_FILE.open("r", encoding="utf-8") as file_handle:
        config = json.load(file_handle)

    return config["salt"]