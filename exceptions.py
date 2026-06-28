"""Custom VaultX exceptions."""

from __future__ import annotations


class VaultError(Exception):
    """Base class for VaultX-specific errors."""


class InvalidPassword(VaultError):
    """Raised when a password cannot decrypt the vault."""


class CorruptedVault(VaultError):
    """Raised when vault contents fail integrity validation."""


class VaultLocked(VaultError):
    """Raised when a lock operation is not valid in the current state."""


class VaultUnlocked(VaultError):
    """Raised when an unlock operation is not valid in the current state."""


class VaultNotFound(VaultError):
    """Raised when expected vault files or folders are missing."""
