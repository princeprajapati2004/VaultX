"""Shared constants for VaultX."""

from __future__ import annotations

import sys
from pathlib import Path

# When running as a PyInstaller executable, __file__ is inside the temp bundle.
# Use sys.executable to get the actual exe location instead.
if getattr(sys, 'frozen', False):
    ROOT_DIR = Path(sys.executable).parent
else:
    ROOT_DIR = Path(__file__).resolve().parent

# v4: Vault container location (single .vxdb file beside executable)
VAULT_CONTAINER_FILE = ROOT_DIR / "Private.vxdb"

# Plaintext working directory when vault is unlocked
VAULT_DIR = ROOT_DIR / "Vault"

# Encrypted files directory (beside executable in v4)
ENCRYPTED_DIR = ROOT_DIR / "Encrypted"

# Encrypted metadata file (stored in Encrypted directory)
METADATA_FILE = ENCRYPTED_DIR / "metadata.json.vx"

# AppData directories for runtime files (logs, temp, backup)
APPDATA_DIR = Path.home() / "AppData" / "Local" / "VaultX"
TEMP_DIR = APPDATA_DIR / "temp"
BACKUP_DIR = APPDATA_DIR / "backup"
LOG_DIR = APPDATA_DIR / "logs"

# Temp/backup paths used during atomic operations
TEMP_VAULT_FILE = TEMP_DIR / "vault.tmp"
BACKUP_VAULT_FILE = BACKUP_DIR / "vault.bak"

LOG_FILE = LOG_DIR / "vault.log"

# Legacy data directory (v2 and earlier — used only for migration detection)
LEGACY_DATA_DIR = ROOT_DIR / "data"
LEGACY_CONFIG_FILE = LEGACY_DATA_DIR / "config.json"
LEGACY_VAULT_FILE = LEGACY_DATA_DIR / "vault.dat"

# Legacy vault data directory (v3 — used for migration)
LEGACY_VAULT_DATA_DIR = ROOT_DIR / "VaultData"
LEGACY_ENCRYPTED_DIR = LEGACY_VAULT_DATA_DIR / "encrypted"
LEGACY_METADATA_DIR = LEGACY_VAULT_DATA_DIR / "metadata"
LEGACY_CONFIG_FILE_V3 = LEGACY_VAULT_DATA_DIR / "config.json"
LEGACY_METADATA_FILE_V3 = LEGACY_VAULT_DATA_DIR / "metadata.json.vx"

APP_VERSION = "4.0.0"
MIN_PASSWORD_LENGTH = 8

# Maximum allowed file size for import: 150 MB
MAX_FILE_SIZE = 150 * 1_024 * 1_024

# XChaCha20-Poly1305 parameters
XCHACHA20_NONCE_SIZE = 24
XCHACHA20_KEY_SIZE = 32
XCHACHA20_TAG_SIZE = 16

# Streaming chunk size: 64 KB
CHUNK_SIZE = 65_536

# Argon2id parameters (OWASP high-value-secret profile)
ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST = 65_536   # 64 MiB
ARGON2_PARALLELISM = 4
ARGON2_HASH_LEN = 32
ARGON2_SALT_LEN = 32

# .vx encrypted file magic and version
VX_MAGIC = b"VXFL"
VX_VERSION = 1

# File extensions that are already compressed — skip zlib compression
ALREADY_COMPRESSED_EXTENSIONS: frozenset[str] = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".mp4", ".mov", ".mkv", ".avi",
    ".mp3", ".aac", ".flac", ".ogg",
    ".zip", ".rar", ".7z", ".gz", ".bz2", ".xz",
    ".pdf",
})

# File extensions that benefit meaningfully from compression
COMPRESSIBLE_EXTENSIONS: frozenset[str] = frozenset({
    ".txt", ".json", ".xml", ".csv", ".log", ".md",
    ".py", ".js", ".ts", ".html", ".css", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".conf",
    ".rs", ".go", ".java", ".c", ".cpp", ".h", ".hpp", ".sh",
})

# ── UI / log messages ─────────────────────────────────────────────────────────

CREATE_NEW_VAULT_MESSAGE = "Create New Vault"
LOCK_VAULT_MESSAGE = "[1] Lock Vault"
UNLOCK_VAULT_MESSAGE = "[1] Unlock Vault"
RECOVERY_TITLE = "--------------------------------"
RECOVERY_MESSAGE = "Recovery detected"
RECOVERY_RECOVER_OPTION = "[1] Recover previous operation"
RECOVERY_DELETE_OPTION = "[2] Delete temporary file"
RECOVERY_PROMPT = "Choose option [1-2]: "
RECOVER_OPTION = "1"
DELETE_TEMP_OPTION = "2"
ENTER_TO_CONTINUE_PROMPT = "Press ENTER to continue: "
CREATE_PASSWORD_PROMPT = "Create Password: "
CONFIRM_PASSWORD_PROMPT = "Confirm Password: "
PASSWORD_PROMPT = "Password: "
PASSWORDS_DO_NOT_MATCH = "Passwords do not match."
PASSWORD_TOO_SHORT = "Password too short."
STARTUP_MESSAGE = "VaultX %s started."
SHUTDOWN_MESSAGE = "VaultX shutting down."
OPERATION_CANCELLED = "Operation cancelled."
LOCKED_MESSAGE = "Vault locked."
UNLOCKED_MESSAGE = "Vault unlocked."
TEMP_FILE_DELETED = "Temporary files deleted."
BACKUP_RESTORED = "Backup restored."
BACKUP_REMOVED = "Backup removed."
BACKUP_CREATED = "Backup created."
VAULT_FOLDER_NOT_FOUND = "Vault folder not found."
NO_VAULT_FOUND = "No vault found."
VAULT_ALREADY_UNLOCKED = "Vault is already unlocked."
WRONG_PASSWORD_OR_CORRUPTED = "Wrong password or corrupted vault."
VAULT_CREATION_FAILED = "Vault creation failed."
LOCK_FAILED = "Failed to lock vault: %s"
UNLOCK_FAILED = "Failed to unlock vault: %s"
RECOVERY_FAILED = "Recovery failed: %s"
RECOVERY_COMPLETE = "Recovery complete."
TEMP_FILE_MISSING = "No temporary files found."
FILE_TOO_LARGE = "File exceeds the 150 MB size limit and cannot be imported."
UNSUPPORTED_FILE = "Unsupported or unsafe file type."
AUTHENTICATION_FAILED = "Authentication tag verification failed — data may be tampered with."
METADATA_CORRUPTED = "Vault metadata is corrupted or incomplete."
CRYPTO_SELF_TEST_FAILED = "Cryptographic self-test failed. VaultX cannot start safely."
LEGACY_VAULT_DETECTED = (
    "Legacy vault format detected (v2 PBKDF2/Fernet).\n\n"
    "To migrate: unlock your vault with VaultX v2, copy files out, "
    "then re-import them with this version."
)
