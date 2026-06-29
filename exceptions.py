"""Custom VaultX exceptions."""

from __future__ import annotations


class VaultError(Exception):
    """Base class for all VaultX-specific errors."""


class InvalidPassword(VaultError):
    """Raised when a password fails authentication."""


class CorruptedVault(VaultError):
    """Raised when vault contents fail integrity validation."""


class VaultLocked(VaultError):
    """Raised when a lock operation is not valid in the current state."""


class VaultUnlocked(VaultError):
    """Raised when an unlock operation is not valid in the current state."""


class VaultNotFound(VaultError):
    """Raised when expected vault files or directories are missing."""


class FileTooLarge(VaultError):
    """Raised when an imported file exceeds the 150 MB size limit."""


class UnsupportedFile(VaultError):
    """Raised when an imported file type is blocked for security reasons."""


class AuthenticationFailed(VaultError):
    """Raised when XChaCha20-Poly1305 authentication tag verification fails."""


class MetadataCorrupted(VaultError):
    """Raised when vault metadata fails decryption or integrity checks."""


class RecoveryRequired(VaultError):
    """Raised when an interrupted operation must be recovered before proceeding."""


class CryptoSelfTestFailed(VaultError):
    """Raised when the startup cryptographic self-test fails."""


class LegacyVaultDetected(VaultError):
    """Raised when a legacy vault format (pre-v3 PBKDF2/Fernet) is detected."""
