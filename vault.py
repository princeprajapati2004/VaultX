"""Per-file vault lock, unlock, and recovery operations for VaultX."""

from __future__ import annotations

import logging
import shutil
import time
import uuid
from pathlib import Path

from constants import (
    BACKUP_CREATED,
    BACKUP_DIR,
    BACKUP_REMOVED,
    BACKUP_RESTORED,
    LOCK_FAILED,
    LOCKED_MESSAGE,
    MAX_FILE_SIZE,
    NO_VAULT_FOUND,
    RECOVERY_COMPLETE,
    RECOVERY_FAILED,
    TEMP_DIR,
    TEMP_FILE_DELETED,
    TEMP_FILE_MISSING,
    UNLOCK_FAILED,
    UNLOCKED_MESSAGE,
    VAULT_ALREADY_UNLOCKED,
    VAULT_DIR,
    VAULT_FOLDER_NOT_FOUND,
    WRONG_PASSWORD_OR_CORRUPTED,
    VAULT_CONTAINER_FILE,
)
from exceptions import (
    CorruptedVault,
    FileTooLarge,
    InvalidPassword,
    MetadataCorrupted,
    VaultNotFound,
    VaultUnlocked,
)
from metadata import (
    FileRecord,
    VaultMetadata,
    build_file_record,
    load_metadata,
    save_metadata,
)
from password_manager import PasswordManager
from streaming import decrypt_file, encrypt_file, should_compress

LOGGER = logging.getLogger(__name__)

_FAILED_ATTEMPTS: dict[str, tuple[float, int]] = {}
_LOCKOUT_DURATION = 30
_CACHED_MEK: bytes | None = None  # Master Encryption Key from unlocked vault


# ── Rate limiting ─────────────────────────────────────────────────────────────

def _check_rate_limit(attempt_key: str = "unlock") -> None:
    """Enforce brute-force rate limiting on failed authentication attempts."""
    now = time.time()
    if attempt_key in _FAILED_ATTEMPTS:
        failed_time, count = _FAILED_ATTEMPTS[attempt_key]
        elapsed = now - failed_time
        if count >= 5 and elapsed < _LOCKOUT_DURATION:
            remaining = int(_LOCKOUT_DURATION - elapsed)
            raise InvalidPassword(
                f"Too many failed attempts. Try again in {remaining} seconds."
            )
        if elapsed >= _LOCKOUT_DURATION:
            del _FAILED_ATTEMPTS[attempt_key]
    current_count = _FAILED_ATTEMPTS.get(attempt_key, (now, 0))[1]
    _FAILED_ATTEMPTS[attempt_key] = (now, current_count + 1)


def _reset_rate_limit(attempt_key: str = "unlock") -> None:
    """Clear the rate-limit counter after a successful authentication."""
    _FAILED_ATTEMPTS.pop(attempt_key, None)


# ── State queries ─────────────────────────────────────────────────────────────

def vault_exists() -> bool:
    """Return True when the vault container exists (Private.vxdb present)."""
    return VAULT_CONTAINER_FILE.exists()


def unlocked() -> bool:
    """Return True when the plaintext Vault/ working directory exists."""
    return VAULT_DIR.exists()


def recovery_pending() -> bool:
    """Return True when temp .vx files from an interrupted lock remain."""
    return TEMP_DIR.exists() and any(TEMP_DIR.glob("*.vx"))


# ── Cleanup helpers ───────────────────────────────────────────────────────────

def delete_temporary_vault() -> None:
    """Delete any .vx temp files left from an interrupted lock operation."""
    if not TEMP_DIR.exists():
        return
    for f in TEMP_DIR.glob("*.vx"):
        f.unlink(missing_ok=True)
    LOGGER.info(TEMP_FILE_DELETED)


def restore_backup_vault() -> None:
    """
    Restore encrypted files from backup when the encrypted directory is empty.

    Called at startup to recover from a crash during a lock operation after
    the original .vx files were moved to backup but before the new ones committed.
    """
    if not BACKUP_DIR.exists():
        return
    backup_files = list(BACKUP_DIR.glob("*.vx"))
    if not backup_files:
        return

    encrypted_has_files = ENCRYPTED_DIR.exists() and any(ENCRYPTED_DIR.glob("*.vx"))
    if encrypted_has_files:
        for f in backup_files:
            f.unlink(missing_ok=True)
        LOGGER.info(BACKUP_REMOVED)
        return

    ENCRYPTED_DIR.mkdir(parents=True, exist_ok=True)
    for f in backup_files:
        f.replace(ENCRYPTED_DIR / f.name)
    LOGGER.info(BACKUP_RESTORED)


# ── Lock ──────────────────────────────────────────────────────────────────────

def lock_vault(password: str) -> None:
    """
    Encrypt each file in Vault/ as a separate .vx object in Encrypted/.

    Per-file pipeline:
      validate → size check → extension policy → generate ID → encrypt (streaming)
      → verify → commit → update metadata → delete Vault/

    Atomic: all new .vx files land in temp/ first, then are committed together.
    Existing encrypted files are backed up before the commit and restored on failure.
    """
    global _CACHED_MEK

    if not unlocked():
        raise VaultNotFound(VAULT_FOLDER_NOT_FOUND)

    # Use the cached MEK from unlock_vault
    if not _CACHED_MEK:
        raise InvalidPassword(WRONG_PASSWORD_OR_CORRUPTED)

    master_key = _CACHED_MEK

    for d in (ENCRYPTED_DIR, TEMP_DIR, BACKUP_DIR):
        d.mkdir(parents=True, exist_ok=True)

    plaintext_files = [f for f in VAULT_DIR.rglob("*") if f.is_file()]
    meta = VaultMetadata()
    temp_written: list[Path] = []
    backup_moved: list[Path] = []

    try:
        # ── Phase 1: validate and encrypt every file to TEMP_DIR ─────────────
        for file_path in plaintext_files:
            size = file_path.stat().st_size
            if size > MAX_FILE_SIZE:
                raise FileTooLarge(
                    f"'{file_path.name}' is {size // (1024*1024)} MB "
                    f"and exceeds the 150 MB limit."
                )

            file_id = str(uuid.uuid4())
            temp_path = TEMP_DIR / f"{file_id}.vx"
            compress = should_compress(file_path)

            LOGGER.info("Encrypting: %s", file_path.name)
            sha256_hex, was_compressed = encrypt_file(
                file_path, temp_path, master_key, file_id, compress=compress
            )
            temp_written.append(temp_path)

            record = build_file_record(
                file_id=file_id,
                original_name=file_path.name,
                plaintext_path=file_path,
                sha256=sha256_hex,
                compressed=was_compressed,
            )
            meta.add_file(record)

        # ── Phase 2: back up existing encrypted files ────────────────────────
        for existing in ENCRYPTED_DIR.glob("*.vx"):
            existing.replace(BACKUP_DIR / existing.name)
            backup_moved.append(BACKUP_DIR / existing.name)
        if backup_moved:
            LOGGER.info(BACKUP_CREATED)

        # ── Phase 3: commit temp files → encrypted dir ───────────────────────
        for temp_path in temp_written:
            temp_path.replace(ENCRYPTED_DIR / temp_path.name)
        temp_written.clear()

        # ── Phase 4: write encrypted metadata ───────────────────────────────
        save_metadata(meta, master_key)

        # ── Phase 5: clean up backup and Vault/ ──────────────────────────────
        for bak in backup_moved:
            bak.unlink(missing_ok=True)
        LOGGER.info(BACKUP_REMOVED)

        shutil.rmtree(VAULT_DIR)
        _CACHED_MEK = None  # Clear cached MEK after successful lock
        LOGGER.info(LOCKED_MESSAGE)

    except Exception as exc:
        LOGGER.error(LOCK_FAILED, exc)
        # Rollback: remove any temp files not yet committed
        for tp in temp_written:
            tp.unlink(missing_ok=True)
        # Restore backup if we already moved the original encrypted files
        if backup_moved and not any(ENCRYPTED_DIR.glob("*.vx")):
            for bak in backup_moved:
                if bak.exists():
                    bak.replace(ENCRYPTED_DIR / bak.name)
            LOGGER.info(BACKUP_RESTORED)
        raise


# ── Unlock ────────────────────────────────────────────────────────────────────

def unlock_vault(password: str) -> None:
    """
    Decrypt all .vx files from Encrypted/ into Vault/.

    Verifies:
      • password via MEK decryption (constant-time)
      • metadata AEAD authentication tag
      • each file's per-chunk Poly1305 tag
      • each file's SHA-256 checksum against metadata

    On any verification failure the partially-extracted Vault/ is removed.
    """
    if unlocked():
        raise VaultUnlocked(VAULT_ALREADY_UNLOCKED)
    if not vault_exists():
        raise VaultNotFound(NO_VAULT_FOUND)

    try:
        _check_rate_limit("unlock")

        # Unlock vault container to get Master Encryption Key
        pm = PasswordManager(VAULT_CONTAINER_FILE)
        if not pm.unlock_vault(password):
            raise InvalidPassword(WRONG_PASSWORD_OR_CORRUPTED)

        master_key = pm.get_mek()
        if not master_key:
            raise InvalidPassword(WRONG_PASSWORD_OR_CORRUPTED)

        LOGGER.info("Verifying metadata.")
        meta = load_metadata(master_key)

        VAULT_DIR.mkdir(parents=True, exist_ok=True)

        try:
            for file_id, record in meta.files.items():
                vx_path = ENCRYPTED_DIR / record.encrypted_name
                if not vx_path.exists():
                    raise VaultNotFound(
                        f"Encrypted file missing from vault: {record.encrypted_name}"
                    )

                dest_path = _unique_path(VAULT_DIR / record.original_name)
                LOGGER.info("Decrypting: %s", record.original_name)
                decrypt_file(
                    vx_path,
                    dest_path,
                    master_key,
                    file_id,
                    expected_sha256=record.sha256,
                )

        except Exception as exc:
            if VAULT_DIR.exists():
                shutil.rmtree(VAULT_DIR)
            raise CorruptedVault(WRONG_PASSWORD_OR_CORRUPTED) from exc

        _reset_rate_limit("unlock")
        global _CACHED_MEK
        _CACHED_MEK = master_key
        LOGGER.info(UNLOCKED_MESSAGE)

    except (InvalidPassword, CorruptedVault, MetadataCorrupted) as exc:
        LOGGER.error(str(exc))
        raise
    except Exception as exc:
        LOGGER.error(UNLOCK_FAILED, exc)
        if VAULT_DIR.exists():
            shutil.rmtree(VAULT_DIR)
        raise


# ── Recovery ──────────────────────────────────────────────────────────────────

def recover_temporary_vault() -> None:
    """
    Recover from an interrupted lock by promoting .vx temp files to encrypted/.

    Called when the app detects recovery_pending() is True at startup.
    """
    if not recovery_pending():
        raise VaultNotFound(TEMP_FILE_MISSING)
    try:
        ENCRYPTED_DIR.mkdir(parents=True, exist_ok=True)
        for temp_file in TEMP_DIR.glob("*.vx"):
            temp_file.replace(ENCRYPTED_DIR / temp_file.name)
        LOGGER.info(RECOVERY_COMPLETE)
    except Exception as exc:
        LOGGER.error(RECOVERY_FAILED, exc)
        raise


# ── Internal helpers ──────────────────────────────────────────────────────────

def _unique_path(path: Path) -> Path:
    """Return *path* unchanged if it does not exist, otherwise append _N suffix."""
    if not path.exists():
        return path
    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1
