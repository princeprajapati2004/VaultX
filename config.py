"""Vault configuration and password management for VaultX v4 (container format)."""

from __future__ import annotations

from constants import (
    BACKUP_DIR,
    ENCRYPTED_DIR,
    LOG_DIR,
    TEMP_DIR,
    VAULT_CONTAINER_FILE,
    VAULT_DIR,
    LEGACY_CONFIG_FILE,
    LEGACY_VAULT_DATA_DIR,
)
from password_manager import PasswordManager
from vault_migration import detect_v3_vault


def _create_vault_directories() -> None:
    """Create the necessary vault runtime directories on first setup."""
    for directory in (
        ENCRYPTED_DIR,
        TEMP_DIR,
        BACKUP_DIR,
        LOG_DIR,
        VAULT_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def save_new_password(password: str) -> None:
    """
    Create a new vault with the given password.

    Creates:
    - Private.vxdb (vault container with MEK)
    - Encrypted/ directory for encrypted files
    - AppData structure for logs/temp/backup
    """
    _create_vault_directories()

    # Create vault container
    pm = PasswordManager(VAULT_CONTAINER_FILE)
    pm.create_vault(password)


def verify_password(password: str) -> bool:
    """
    Verify password against the vault container.

    Returns True if password is correct, False otherwise.
    No password hash comparison - just MEK decryption verification.
    """
    pm = PasswordManager(VAULT_CONTAINER_FILE)
    return pm.unlock_vault(password)


def get_master_key(password: str) -> bytes:
    """
    Derive and return the Master Encryption Key for the password.

    Must only be called after verify_password succeeds.
    """
    pm = PasswordManager(VAULT_CONTAINER_FILE)
    if not pm.unlock_vault(password):
        raise ValueError("Invalid password")
    mek = pm.get_mek()
    if not mek:
        raise ValueError("Failed to retrieve MEK")
    return mek


def is_legacy_vault() -> bool:
    """
    Return True when a legacy vault format is detected.

    Detects:
    - v2 (PBKDF2/Fernet) with data/config.json
    - v3 (Argon2id) with VaultData/config.json
    """
    legacy_v2 = LEGACY_CONFIG_FILE.exists()
    legacy_v3 = detect_v3_vault()
    return legacy_v2 or legacy_v3
