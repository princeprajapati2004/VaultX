"""Vault lock, unlock, and recovery logic for VaultX."""

from __future__ import annotations

import logging
import shutil
import time

from cryptography.fernet import InvalidToken

from archive import bytes_to_folder, folder_to_bytes, is_valid_zip_bytes
from config import get_salt, verify_password
from constants import (
    BACKUP_CREATED,
    BACKUP_REMOVED,
    BACKUP_RESTORED,
    BACKUP_VAULT_FILE,
    LOCKED_MESSAGE,
    LOCK_FAILED,
    NO_VAULT_FOUND,
    RECOVERY_COMPLETE,
    RECOVERY_FAILED,
    TEMP_FILE_MISSING,
    TEMP_VAULT_FILE,
    TEMP_FILE_DELETED,
    UNLOCKED_MESSAGE,
    UNLOCK_FAILED,
    VAULT_ALREADY_UNLOCKED,
    VAULT_DIR,
    VAULT_FILE,
    VAULT_FOLDER_NOT_FOUND,
    WRONG_PASSWORD_OR_CORRUPTED,
)
from exceptions import CorruptedVault, InvalidPassword, VaultLocked, VaultNotFound, VaultUnlocked
from crypto import decrypt_bytes, encrypt_bytes

LOGGER = logging.getLogger(__name__)

_FAILED_ATTEMPTS = {}
_LOCKOUT_DURATION = 30


def _check_rate_limit(attempt_key: str = "unlock") -> None:
    """Enforce rate limiting on failed authentication attempts."""

    now = time.time()

    if attempt_key in _FAILED_ATTEMPTS:
        failed_time, count = _FAILED_ATTEMPTS[attempt_key]
        elapsed = now - failed_time

        if count >= 5 and elapsed < _LOCKOUT_DURATION:
            raise InvalidPassword(f"Too many failed attempts. Try again in {int(_LOCKOUT_DURATION - elapsed)} seconds.")

        if elapsed >= _LOCKOUT_DURATION:
            del _FAILED_ATTEMPTS[attempt_key]

    _FAILED_ATTEMPTS[attempt_key] = (now, _FAILED_ATTEMPTS.get(attempt_key, (now, 0))[1] + 1)


def _reset_rate_limit(attempt_key: str = "unlock") -> None:
    """Clear failed attempt tracking on successful authentication."""

    if attempt_key in _FAILED_ATTEMPTS:
        del _FAILED_ATTEMPTS[attempt_key]


def vault_exists() -> bool:
    """Return True when the encrypted vault file exists."""

    return VAULT_FILE.exists()


def unlocked() -> bool:
    """Return True when the vault folder is currently available."""

    return VAULT_DIR.exists()


def recovery_pending() -> bool:
    """Return True when a temporary vault file exists."""

    return TEMP_VAULT_FILE.exists()


def delete_temporary_vault() -> None:
    """Delete the temporary vault file if one exists."""

    if TEMP_VAULT_FILE.exists():
        TEMP_VAULT_FILE.unlink()
        LOGGER.info(TEMP_FILE_DELETED)


def restore_backup_vault() -> None:
    """Restore or clean up the backup vault file."""

    if not BACKUP_VAULT_FILE.exists():
        return

    if vault_exists():
        BACKUP_VAULT_FILE.unlink()
        LOGGER.info(BACKUP_REMOVED)
        return

    BACKUP_VAULT_FILE.replace(VAULT_FILE)
    LOGGER.info(BACKUP_RESTORED)


def _ensure_data_dir() -> None:
    """Create the data directory if required."""

    VAULT_FILE.parent.mkdir(parents=True, exist_ok=True)


def _verify_encrypted_archive(encrypted_blob: bytes, password: str) -> bytes:
    """Decrypt and validate encrypted vault bytes in memory."""

    try:
        decrypted = decrypt_bytes(encrypted_blob, password, get_salt())
    except InvalidToken as exc:
        raise InvalidPassword(WRONG_PASSWORD_OR_CORRUPTED) from exc

    if not is_valid_zip_bytes(decrypted):
        raise CorruptedVault(WRONG_PASSWORD_OR_CORRUPTED)

    return decrypted


def recover_temporary_vault() -> None:
    """Recover a previously interrupted lock operation."""

    if not TEMP_VAULT_FILE.exists():
        raise VaultNotFound(TEMP_FILE_MISSING)

    try:
        temp_blob = TEMP_VAULT_FILE.read_bytes()
        if not temp_blob:
            raise CorruptedVault(TEMP_FILE_MISSING)

        if VAULT_FILE.exists() and not BACKUP_VAULT_FILE.exists():
            VAULT_FILE.replace(BACKUP_VAULT_FILE)
            LOGGER.info(BACKUP_CREATED)

        TEMP_VAULT_FILE.replace(VAULT_FILE)

        if not VAULT_FILE.exists() or VAULT_FILE.stat().st_size == 0:
            raise CorruptedVault(RECOVERY_FAILED)

        if BACKUP_VAULT_FILE.exists():
            BACKUP_VAULT_FILE.unlink()
            LOGGER.info(BACKUP_REMOVED)

        LOGGER.info(RECOVERY_COMPLETE)

    except Exception as exc:
        LOGGER.error(RECOVERY_FAILED, exc)

        if BACKUP_VAULT_FILE.exists():
            BACKUP_VAULT_FILE.replace(VAULT_FILE)
            LOGGER.info(BACKUP_RESTORED)

        raise


def lock_vault(password: str) -> None:
    """Archive and encrypt the vault folder."""

    if not unlocked():
        raise VaultNotFound(VAULT_FOLDER_NOT_FOUND)

    _ensure_data_dir()
    backup_created = False

    try:
        LOGGER.info("Creating archive.")
        data = folder_to_bytes(VAULT_DIR)

        LOGGER.info("Encrypting.")
        encrypted = encrypt_bytes(data, password, get_salt())
        TEMP_VAULT_FILE.write_bytes(encrypted)

        if not TEMP_VAULT_FILE.exists() or TEMP_VAULT_FILE.stat().st_size == 0:
            raise CorruptedVault(TEMP_FILE_MISSING)

        _verify_encrypted_archive(TEMP_VAULT_FILE.read_bytes(), password)

        if VAULT_FILE.exists():
            if BACKUP_VAULT_FILE.exists():
                BACKUP_VAULT_FILE.unlink()

            LOGGER.info(BACKUP_CREATED)
            VAULT_FILE.replace(BACKUP_VAULT_FILE)
            backup_created = True

        TEMP_VAULT_FILE.replace(VAULT_FILE)
        _verify_encrypted_archive(VAULT_FILE.read_bytes(), password)

        if BACKUP_VAULT_FILE.exists():
            BACKUP_VAULT_FILE.unlink()
            LOGGER.info(BACKUP_REMOVED)

        shutil.rmtree(VAULT_DIR)
        LOGGER.info(LOCKED_MESSAGE)

    except InvalidPassword:
        LOGGER.error(WRONG_PASSWORD_OR_CORRUPTED)
        if TEMP_VAULT_FILE.exists():
            TEMP_VAULT_FILE.unlink()
        if backup_created and BACKUP_VAULT_FILE.exists():
            BACKUP_VAULT_FILE.replace(VAULT_FILE)
            LOGGER.info(BACKUP_RESTORED)
        raise

    except (CorruptedVault, VaultNotFound, VaultLocked) as exc:
        LOGGER.error(LOCK_FAILED, exc)
        if TEMP_VAULT_FILE.exists():
            TEMP_VAULT_FILE.unlink()
        if backup_created and BACKUP_VAULT_FILE.exists():
            BACKUP_VAULT_FILE.replace(VAULT_FILE)
            LOGGER.info(BACKUP_RESTORED)
        raise

    except Exception as exc:
        LOGGER.error(LOCK_FAILED, exc)
        if TEMP_VAULT_FILE.exists():
            TEMP_VAULT_FILE.unlink()
        if backup_created and BACKUP_VAULT_FILE.exists():
            BACKUP_VAULT_FILE.replace(VAULT_FILE)
            LOGGER.info(BACKUP_RESTORED)
        raise


def unlock_vault(password: str) -> None:
    """Decrypt and restore the vault folder from disk."""

    if unlocked():
        raise VaultUnlocked(VAULT_ALREADY_UNLOCKED)

    if not vault_exists():
        raise VaultNotFound(NO_VAULT_FOUND)

    try:
        _check_rate_limit("unlock")

        if not verify_password(password):
            raise InvalidPassword(WRONG_PASSWORD_OR_CORRUPTED)

        encrypted = VAULT_FILE.read_bytes()
        LOGGER.info("Decrypting.")
        decrypted = _verify_encrypted_archive(encrypted, password)

        VAULT_DIR.mkdir(parents=True, exist_ok=False)

        try:
            bytes_to_folder(decrypted, VAULT_DIR)
        except Exception as exc:
            if VAULT_DIR.exists():
                shutil.rmtree(VAULT_DIR)
            raise CorruptedVault(WRONG_PASSWORD_OR_CORRUPTED) from exc

        _reset_rate_limit("unlock")
        LOGGER.info(UNLOCKED_MESSAGE)

    except (InvalidPassword, CorruptedVault) as exc:
        LOGGER.error(str(exc))
        raise

    except Exception as exc:
        LOGGER.error(UNLOCK_FAILED, exc)
        if VAULT_DIR.exists():
            shutil.rmtree(VAULT_DIR)
        raise