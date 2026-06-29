"""Password management for vault container - no password hashes stored."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from vault_container import VaultContainer


class PasswordManager:
    """Manages vault passwords without storing password hashes.

    Password verification works by:
    1. Attempting to decrypt the MEK with the provided password
    2. If decryption succeeds, password is correct
    3. If decryption fails, password is wrong

    Password changes only re-encrypt the MEK, not all files.
    """

    def __init__(self, vault_path: Path):
        """Initialize password manager for a vault."""
        self.vault_path = Path(vault_path)
        self.container = VaultContainer(vault_path)

    def vault_exists(self) -> bool:
        """Check if vault exists."""
        return self.vault_path.exists()

    def create_vault(self, password: str) -> bool:
        """Create a new vault with the given password."""
        if self.vault_path.exists():
            return False

        try:
            self.container.create(password)
            return True
        except Exception:
            return False

    def unlock_vault(self, password: str) -> bool:
        """
        Attempt to unlock vault with password.

        Returns True if password is correct, False otherwise.
        No password hash comparison - just MEK decryption verification.
        """
        try:
            return self.container.unlock(password)
        except Exception:
            return False

    def is_unlocked(self) -> bool:
        """Check if vault is currently unlocked."""
        return self.container.is_unlocked()

    def lock_vault(self) -> None:
        """Lock the vault."""
        self.container.lock()

    def change_password(self, old_password: str, new_password: str) -> bool:
        """
        Change vault password.

        Does NOT re-encrypt any files - only updates the MEK encryption.
        Should complete in under 1 second regardless of vault size.
        """
        return self.container.change_password(old_password, new_password)

    def get_mek(self) -> Optional[bytes]:
        """Get the decrypted Master Encryption Key."""
        return self.container.get_mek()
