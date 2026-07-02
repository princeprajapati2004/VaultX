#!/usr/bin/env python3
"""Emergency reset script - deletes all vault files for a fresh start."""

from pathlib import Path
import shutil
import sys

def reset_vault():
    """Remove all vault files and start fresh."""
    base_dir = Path(__file__).parent
    paths_to_remove = [
        base_dir / "Private.vxdb",
        base_dir / "Vault",
        base_dir / "Encrypted",
        base_dir / "AppData" / "vaultx" / "temp",
        base_dir / "AppData" / "vaultx" / "backup",
    ]

    removed_count = 0
    for path in paths_to_remove:
        if path.exists():
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                print(f"✓ Removed: {path.name}")
                removed_count += 1
            except Exception as e:
                print(f"✗ Failed to remove {path.name}: {e}")
                return False

    if removed_count > 0:
        print(f"\n✓ Reset complete! Removed {removed_count} items.")
        print("You can now run main.py to create a fresh vault.")
        return True
    else:
        print("No vault files found to remove.")
        return True

if __name__ == "__main__":
    try:
        success = reset_vault()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nReset cancelled.")
        sys.exit(1)
