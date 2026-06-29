"""Secure file import handler for VaultX."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from zipfile import ZipFile

from config import verify_password
from constants import VAULT_DIR

LOGGER = logging.getLogger(__name__)


def import_files(file_paths: list[str], password: str) -> None:
    """
    Import files into the vault with password verification.

    Args:
        file_paths: List of file/folder paths to import
        password: Master password for verification

    Raises:
        InvalidPassword: If password is incorrect
        ValueError: If vault is not unlocked or import fails
    """

    if not verify_password(password):
        raise ValueError("Invalid password.")

    if not VAULT_DIR.exists():
        raise ValueError("Vault must be unlocked before importing files.")

    imported_count = 0

    for file_path in file_paths:
        source = Path(file_path)

        if not source.exists():
            LOGGER.warning(f"File not found: {file_path}")
            continue

        try:
            if source.is_file():
                _import_file(source)
                imported_count += 1
            elif source.is_dir():
                _import_directory(source)
                imported_count += 1
        except Exception as exc:
            LOGGER.error(f"Failed to import {file_path}: {exc}")

    if imported_count == 0:
        raise ValueError("No files were imported.")

    LOGGER.info(f"Successfully imported {imported_count} item(s) to vault.")


def _import_file(source: Path) -> None:
    """Copy a single file to the vault."""

    destination = VAULT_DIR / source.name

    if destination.exists():
        counter = 1
        stem = source.stem
        suffix = source.suffix
        while (VAULT_DIR / f"{stem}_{counter}{suffix}").exists():
            counter += 1
        destination = VAULT_DIR / f"{stem}_{counter}{suffix}"

    shutil.copy2(source, destination)
    LOGGER.info(f"Imported file: {source.name} → {destination.name}")


def _import_directory(source: Path) -> None:
    """Copy a directory and all its contents to the vault."""

    destination = VAULT_DIR / source.name

    if destination.exists():
        counter = 1
        while (VAULT_DIR / f"{source.name}_{counter}").exists():
            counter += 1
        destination = VAULT_DIR / f"{source.name}_{counter}"

    shutil.copytree(source, destination, dirs_exist_ok=True)
    LOGGER.info(f"Imported directory: {source.name} → {destination.name}")


def validate_file_safety(file_path: str) -> tuple[bool, str]:
    """
    Validate that a file is safe to import.

    Returns:
        (is_safe, reason) - Tuple of validation result and explanation
    """

    source = Path(file_path)

    if not source.exists():
        return False, "File does not exist"

    if source.is_symlink():
        return False, "Symbolic links are not allowed (potential security risk)"

    if source.stat().st_size > 5_000_000_000:
        return False, "File exceeds 5GB size limit"

    if source.is_file() and source.suffix.lower() in {".exe", ".dll", ".sys", ".bat", ".cmd", ".ps1"}:
        return False, "Executable files are not allowed for security reasons"

    return True, "File is safe to import"
