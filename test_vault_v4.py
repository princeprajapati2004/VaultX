"""Quick integration test for VaultX v4 vault container."""

from __future__ import annotations

import tempfile
from pathlib import Path

# Test 1: Basic vault creation and password verification
def test_vault_creation():
    """Test creating a new vault and verifying passwords."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "test.vxdb"

        from vault_container import VaultContainer

        container = VaultContainer(vault_path)

        # Create new vault
        mek = container.create("test_password_123")
        assert mek is not None
        assert len(mek) == 32
        print("✓ Vault creation successful")

        # Verify vault file exists
        assert vault_path.exists()
        print("✓ Vault file created")

        # Try unlocking with correct password
        container2 = VaultContainer(vault_path)
        assert container2.unlock("test_password_123")
        assert container2.get_mek() is not None
        print("✓ Correct password verification works")

        # Try unlocking with wrong password
        container3 = VaultContainer(vault_path)
        assert not container3.unlock("wrong_password")
        assert container3.get_mek() is None
        print("✓ Wrong password rejection works")


# Test 2: Password change
def test_password_change():
    """Test changing password without re-encryption."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "test.vxdb"

        from vault_container import VaultContainer

        # Create vault
        container = VaultContainer(vault_path)
        original_mek = container.create("old_password")

        # Change password
        assert container.change_password("old_password", "new_password")
        print("✓ Password change successful")

        # Verify old password no longer works
        container2 = VaultContainer(vault_path)
        assert not container2.unlock("old_password")
        print("✓ Old password rejected after change")

        # Verify new password works
        container3 = VaultContainer(vault_path)
        assert container3.unlock("new_password")
        new_mek = container3.get_mek()

        # MEK should still be the same (only KEK changed)
        assert new_mek == original_mek
        print("✓ MEK unchanged after password change")


# Test 3: PasswordManager integration
def test_password_manager():
    """Test PasswordManager wrapper."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "test.vxdb"

        from password_manager import PasswordManager

        pm = PasswordManager(vault_path)

        # Vault shouldn't exist yet
        assert not pm.vault_exists()

        # Create vault
        assert pm.create_vault("my_password")
        assert pm.vault_exists()
        print("✓ PasswordManager vault creation works")

        # Verify unlock
        pm2 = PasswordManager(vault_path)
        assert pm2.unlock_vault("my_password")
        assert pm2.is_unlocked()
        print("✓ PasswordManager unlock works")

        # Get MEK
        mek = pm2.get_mek()
        assert mek is not None
        assert len(mek) == 32
        print("✓ PasswordManager MEK retrieval works")

        # Lock
        pm2.lock_vault()
        assert not pm2.is_unlocked()
        print("✓ PasswordManager lock works")


if __name__ == "__main__":
    print("Running VaultX v4 integration tests...\n")

    try:
        test_vault_creation()
        print()
        test_password_change()
        print()
        test_password_manager()
        print("\n✅ All tests passed!")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
