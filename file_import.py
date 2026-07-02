"""Secure file import handler for VaultX.

Import pipeline (per file):
  1. Validate existence and type
  2. File size check (≤ 150 MB)
  3. Extension policy (block executables / symlinks)
  4. Copy to Vault/ working directory
  5. Files are encrypted into VaultData/encrypted/ at the next lock_vault() call
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from config import verify_password
from constants import MAX_FILE_SIZE, VAULT_DIR
from exceptions import FileTooLarge, InvalidPassword, UnsupportedFile

LOGGER = logging.getLogger(__name__)

_BLOCKED_EXTENSIONS: frozenset[str] = frozenset({
    ".exe", ".dll", ".sys", ".bat", ".cmd", ".ps1",
    ".msi", ".scr", ".vbs", ".vbe", ".js", ".jse",
    ".wsf", ".wsh", ".pif", ".com", ".gadget",
})


def validate_file_safety(file_path: str) -> tuple[bool, str]:
    """
    Validate that a file is safe and within policy to import.

    Returns:
        (is_safe: bool, reason: str)
    """
    source = Path(file_path)

    if not source.exists():
        return False, "File or folder does not exist."

    if source.is_symlink():
        return False, "Symbolic links are not allowed."

    if source.is_file():
        size = source.stat().st_size
        if size > MAX_FILE_SIZE:
            mb = size // (1024 * 1024)
            return False, f"File is {mb} MB — exceeds the 150 MB limit."

        if source.suffix.lower() in _BLOCKED_EXTENSIONS:
            return False, f"Executable file type '{source.suffix}' is not allowed."

    return True, "File is safe to import."


def import_files(file_paths: list[str], password: str) -> None:
    """
    Import files or folders into the unlocked Vault/ working directory.

    Validates password, applies size and extension policy per item,
    then copies each item into Vault/.  Encryption occurs at the next lock.

    Raises:
        InvalidPassword: password does not match
        ValueError: vault is not unlocked or no files could be imported
        FileTooLarge: a file exceeds the 150 MB limit
        UnsupportedFile: a blocked extension was submitted
    """
    if not verify_password(password):
        raise InvalidPassword("Invalid password.")

    if not VAULT_DIR.exists():
        raise ValueError("Vault must be unlocked before importing files.")

    imported = 0

    for file_path in file_paths:
        source = Path(file_path)
        if not source.exists():
            LOGGER.warning("Import skipped — not found: %s", file_path)
            continue

        is_safe, reason = validate_file_safety(file_path)
        if not is_safe:
            if "150 MB" in reason:
                raise FileTooLarge(reason)
            if "Executable" in reason:
                raise UnsupportedFile(reason)
            LOGGER.warning("Import blocked (%s): %s", reason, file_path)
            continue

        try:
            if source.is_file():
                _import_single_file(source)
            elif source.is_dir():
                _import_directory(source)
            imported += 1
        except (FileTooLarge, UnsupportedFile):
            raise
        except Exception as exc:
            LOGGER.error("Failed to import '%s': %s", file_path, exc)

    if imported == 0:
        raise ValueError("No files were successfully imported.")

    LOGGER.info("Imported %d item(s) into Vault/.", imported)


def _import_single_file(source: Path) -> None:
    """Copy one file into Vault/, renaming on conflict."""
    dest = _unique_destination(VAULT_DIR / source.name)
    shutil.copy2(source, dest)
    LOGGER.info("Imported: %s → %s", source.name, dest.name)


def _import_directory(source: Path) -> None:
    """Copy a directory tree into Vault/ after validating every file inside."""
    # Walk tree first so we can reject the whole import before writing anything
    for child in source.rglob("*"):
        if child.is_symlink():
            raise UnsupportedFile(f"Symbolic link inside directory not allowed: {child.name}")
        if child.is_file():
            size = child.stat().st_size
            if size > MAX_FILE_SIZE:
                mb = size // (1024 * 1024)
                raise FileTooLarge(
                    f"'{child.name}' is {mb} MB and exceeds the 150 MB limit."
                )
            if child.suffix.lower() in _BLOCKED_EXTENSIONS:
                raise UnsupportedFile(
                    f"Executable file type '{child.suffix}' inside directory is not allowed."
                )

    dest = _unique_destination(VAULT_DIR / source.name)
    shutil.copytree(source, dest, symlinks=False)
    LOGGER.info("Imported directory: %s → %s", source.name, dest.name)


def _unique_destination(path: Path) -> Path:
    """Return *path* if it doesn't exist, otherwise append _N suffix."""
    if not path.exists():
        return path
    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1
