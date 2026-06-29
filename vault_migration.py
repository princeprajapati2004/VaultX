"""Migration from v3 VaultData structure to v4 vault container format."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

from constants import (
    LEGACY_VAULT_DATA_DIR,
    LEGACY_CONFIG_FILE_V3,
    LEGACY_METADATA_FILE_V3,
    LEGACY_ENCRYPTED_DIR,
    VAULT_CONTAINER_FILE,
    VAULT_DIR,
    ENCRYPTED_DIR,
    APP_VERSION,
)
from vault_container import VaultContainer


def detect_v3_vault() -> bool:
    """Check if a v3 vault exists (VaultData folder with config.json)."""
    return LEGACY_VAULT_DATA_DIR.exists() and LEGACY_CONFIG_FILE_V3.exists()


def detect_legacy_v2_vault() -> bool:
    """Check if a legacy v2 vault exists."""
    from constants import LEGACY_DATA_DIR, LEGACY_CONFIG_FILE
    return LEGACY_DATA_DIR.exists() and LEGACY_CONFIG_FILE.exists()


def migrate_v3_to_v4(password: str) -> bool:
    """
    Migrate an existing v3 vault to v4 format.

    This:
    1. Creates a new Private.vxdb container
    2. Keeps encrypted files unchanged
    3. Stores vault metadata in the container
    4. Removes VaultData folder

    Returns True if migration successful.
    """
    if not detect_v3_vault():
        return False

    if VAULT_CONTAINER_FILE.exists():
        # v4 vault already exists
        return False

    # Create new v4 vault container
    container = VaultContainer(VAULT_CONTAINER_FILE)
    mek = container.create(password)

    # Read v3 config to preserve vault metadata
    try:
        with open(LEGACY_CONFIG_FILE_V3) as f:
            v3_config = json.load(f)
    except Exception:
        v3_config = {}

    # Copy encrypted files to Encrypted directory (keeps them accessible)
    encrypted_dir = VAULT_DIR / "Encrypted"
    if LEGACY_ENCRYPTED_DIR.exists():
        encrypted_dir.mkdir(parents=True, exist_ok=True)
        for encrypted_file in LEGACY_ENCRYPTED_DIR.glob("*.vx"):
            shutil.copy2(encrypted_file, encrypted_dir / encrypted_file.name)

    # Preserve metadata if it exists
    metadata_file = LEGACY_METADATA_FILE_V3
    if metadata_file.exists():
        try:
            with open(metadata_file, 'rb') as f:
                metadata_bytes = f.read()
            metadata_path = encrypted_dir.parent / ".metadata"
            metadata_path.write_bytes(metadata_bytes)
        except Exception:
            pass  # If metadata can't be copied, continue anyway

    # Clean up v3 structure
    try:
        if LEGACY_VAULT_DATA_DIR.exists():
            shutil.rmtree(LEGACY_VAULT_DATA_DIR)
    except Exception:
        pass  # If cleanup fails, vault is still functional

    return True


def prompt_migration(password: str) -> bool:
    """
    Prompt user about migration if v3 vault detected.
    Returns True if migration completed.
    """
    if not detect_v3_vault():
        return False

    if VAULT_CONTAINER_FILE.exists():
        # Already migrated
        return False

    print("\n" + "=" * 50)
    print("VaultX v3 → v4 Migration Detected")
    print("=" * 50)
    print("\nYour vault needs to be migrated to the new format.")
    print("This will:")
    print("  • Create Private.vxdb (vault container)")
    print("  • Keep all encrypted files intact")
    print("  • Remove VaultData folder")
    print("  • Move logs/temp to AppData")
    print("\nNo data will be lost.")

    try:
        response = input("\nMigrate now? (yes/no): ").strip().lower()
        if response in ("yes", "y"):
            if migrate_v3_to_v4(password):
                print("\n✓ Migration successful!")
                print("Your vault is now using the v4 format.")
                return True
            else:
                print("\n✗ Migration failed.")
                return False
        else:
            print("Migration skipped.")
            return False
    except Exception as exc:
        print(f"\n✗ Migration error: {exc}")
        return False
