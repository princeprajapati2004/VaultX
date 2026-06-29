#!/usr/bin/env python3
"""
Recovery script to reset VaultX if vault file is corrupted.
Run this script if you're stuck on the password screen on first startup.
"""

from pathlib import Path
import shutil
import sys

def reset_vault():
    """Remove corrupted vault and reset to initial state."""
    vault_dir = Path(__file__).resolve().parent
    vault_container = vault_dir / "Private.vxdb"
    vault_data = vault_dir / "Vault"
    appdata_dir = Path.home() / "AppData" / "Local" / "VaultX"

    print("VaultX Vault Recovery Tool")
    print("=" * 50)
    print()
    print("This script will:")
    print("  1. Delete the corrupted vault container (Private.vxdb)")
    print("  2. Clear temp/backup files")
    print("  3. Allow you to create a new vault fresh")
    print()
    print("All encrypted files will be preserved in Encrypted/ folder.")
    print()

    response = input("Continue with reset? (yes/no): ").strip().lower()
    if response not in ("yes", "y"):
        print("Reset cancelled.")
        return False

    try:
        # Remove corrupted vault file
        if vault_container.exists():
            vault_container.unlink()
            print(f"✓ Deleted {vault_container.name}")

        # Remove temp files
        if appdata_dir.exists():
            temp_dir = appdata_dir / "temp"
            backup_dir = appdata_dir / "backup"

            if temp_dir.exists():
                shutil.rmtree(temp_dir)
                print(f"✓ Cleared temp directory")

            if backup_dir.exists():
                shutil.rmtree(backup_dir)
                print(f"✓ Cleared backup directory")

        print()
        print("✅ Vault reset complete!")
        print()
        print("Next steps:")
        print("  1. Run 'python main.py' to start VaultX")
        print("  2. You'll see the 'Welcome' screen")
        print("  3. Click 'Create Vault' to set a new password")
        print()
        return True

    except Exception as exc:
        print(f"❌ Error during reset: {exc}")
        return False

if __name__ == "__main__":
    success = reset_vault()
    sys.exit(0 if success else 1)
