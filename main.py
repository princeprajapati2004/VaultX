"""VaultX application entry point with cryptographic self-test and migration."""

from __future__ import annotations


def main() -> None:
    # Run self-test before touching any UI so a bad build fails loudly
    try:
        from crypto import run_self_test
        run_self_test()
    except Exception as exc:  # noqa: BLE001
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "VaultX — Fatal Error",
            f"Cryptographic self-test failed.\n\n{exc}\n\nVaultX cannot start.",
        )
        root.destroy()
        return

    # Check if migration from v3 to v4 is needed
    try:
        from vault_migration import detect_v3_vault, migrate_v3_to_v4
        from constants import VAULT_CONTAINER_FILE

        if detect_v3_vault() and not VAULT_CONTAINER_FILE.exists():
            import tkinter as tk
            from tkinter import simpledialog, messagebox

            root = tk.Tk()
            root.withdraw()

            password = simpledialog.askstring(
                "VaultX v3 → v4 Migration",
                "A v3 vault was detected.\n\nEnter your password to migrate to v4:",
                show="•",
            )
            root.destroy()

            if password:
                try:
                    if migrate_v3_to_v4(password):
                        messagebox.showinfo(
                            "Migration Complete",
                            "Your vault has been successfully migrated to v4.",
                        )
                    else:
                        messagebox.showerror(
                            "Migration Failed",
                            "Failed to migrate vault. Check that your password is correct.",
                        )
                        return
                except Exception as exc:
                    messagebox.showerror(
                        "Migration Error",
                        f"Migration failed:\n\n{exc}",
                    )
                    return
            else:
                messagebox.showinfo(
                    "Migration Skipped",
                    "You can migrate your vault later.",
                )
    except Exception as exc:
        print(f"Migration check failed: {exc}")

    from ui import run
    run()


if __name__ == "__main__":
    main()
