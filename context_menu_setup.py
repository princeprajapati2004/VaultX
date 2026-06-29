"""Windows context menu integration for VaultX (Run with Administrator privileges)."""

from __future__ import annotations

import sys
import winreg
from pathlib import Path


def register_context_menu(exe_path: str | None = None) -> bool:
    """
    Register VaultX in Windows right-click context menu.

    This requires administrator privileges to modify the registry.
    The context menu will add "Add to VaultX" option when right-clicking files/folders.

    Args:
        exe_path: Path to VaultX.exe (if None, uses current directory)

    Returns:
        True if registration successful, False otherwise
    """

    if exe_path is None:
        exe_path = str(Path(__file__).parent / "VaultX.exe")

    if not Path(exe_path).exists():
        print(f"Error: VaultX.exe not found at {exe_path}")
        return False

    try:
        registry_key = r"*\shell\AddToVaultX"
        reg_path = winreg.HKEY_CLASSES_ROOT

        with winreg.CreateKey(reg_path, registry_key) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "Add to VaultX")
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, f'"{exe_path}",0')

        command_key = registry_key + r"\command"
        with winreg.CreateKey(reg_path, command_key) as key:
            command = f'"{exe_path}" --import "%1"'
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)

        folder_key = r"Directory\shell\AddToVaultX"
        with winreg.CreateKey(reg_path, folder_key) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "Add to VaultX")
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, f'"{exe_path}",0')

        folder_command_key = folder_key + r"\command"
        with winreg.CreateKey(reg_path, folder_command_key) as key:
            command = f'"{exe_path}" --import "%1"'
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)

        print("✓ VaultX context menu registered successfully")
        print("  You can now right-click any file or folder and select 'Add to VaultX'")
        return True

    except PermissionError:
        print("Error: Administrator privileges required to register context menu")
        print("Please run VaultX as Administrator or use the setup wizard")
        return False
    except Exception as exc:
        print(f"Error registering context menu: {exc}")
        return False


def unregister_context_menu() -> bool:
    """
    Remove VaultX from Windows right-click context menu.

    This requires administrator privileges.

    Returns:
        True if unregistration successful, False otherwise
    """

    try:
        reg_path = winreg.HKEY_CLASSES_ROOT

        keys_to_remove = [
            r"*\shell\AddToVaultX",
            r"Directory\shell\AddToVaultX",
        ]

        for key_path in keys_to_remove:
            try:
                winreg.DeleteTree(reg_path, key_path)
            except FileNotFoundError:
                pass

        print("✓ VaultX context menu removed successfully")
        return True

    except PermissionError:
        print("Error: Administrator privileges required to unregister context menu")
        return False
    except Exception as exc:
        print(f"Error unregistering context menu: {exc}")
        return False


def is_registered() -> bool:
    """Check if VaultX is already registered in context menu."""

    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"*\shell\AddToVaultX"):
            return True
    except FileNotFoundError:
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--unregister":
            unregister_context_menu()
        elif sys.argv[1] == "--register":
            if len(sys.argv) > 2:
                register_context_menu(sys.argv[2])
            else:
                register_context_menu()
        elif sys.argv[1] == "--check":
            if is_registered():
                print("VaultX context menu is registered")
            else:
                print("VaultX context menu is NOT registered")
    else:
        print("VaultX Context Menu Setup Tool")
        print("\nUsage:")
        print("  context_menu_setup.py --register [exe_path]  - Register context menu")
        print("  context_menu_setup.py --unregister          - Remove context menu")
        print("  context_menu_setup.py --check               - Check if registered")
        print("\nNote: Requires administrator privileges")
