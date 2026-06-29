"""CustomTkinter user interface for VaultX."""

from __future__ import annotations

import logging
import os
import queue
import threading
from typing import Callable
from tkinter import BooleanVar, TclError

import customtkinter as ctk

from config import is_legacy_vault, save_new_password
from constants import (
    APP_VERSION,
    CREATE_NEW_VAULT_MESSAGE,
    CREATE_PASSWORD_PROMPT,
    CONFIRM_PASSWORD_PROMPT,
    DELETE_TEMP_OPTION,
    ENTER_TO_CONTINUE_PROMPT,
    LEGACY_VAULT_DETECTED,
    LOCK_VAULT_MESSAGE,
    LOG_DIR,
    LOG_FILE,
    MIN_PASSWORD_LENGTH,
    NO_VAULT_FOUND,
    OPERATION_CANCELLED,
    PASSWORD_PROMPT,
    PASSWORDS_DO_NOT_MATCH,
    PASSWORD_TOO_SHORT,
    RECOVER_OPTION,
    RECOVERY_DELETE_OPTION,
    RECOVERY_MESSAGE,
    RECOVERY_PROMPT,
    RECOVERY_RECOVER_OPTION,
    RECOVERY_TITLE,
    SHUTDOWN_MESSAGE,
    STARTUP_MESSAGE,
    TEMP_FILE_DELETED,
    TEMP_FILE_MISSING,
    UNLOCK_VAULT_MESSAGE,
    UNLOCKED_MESSAGE,
    VAULT_ALREADY_UNLOCKED,
    VAULT_CREATION_FAILED,
    VAULT_CONTAINER_FILE,
    ENCRYPTED_DIR,
    VAULT_DIR,
    VAULT_FOLDER_NOT_FOUND,
    WRONG_PASSWORD_OR_CORRUPTED,
)
from exceptions import (
    CorruptedVault,
    FileTooLarge,
    InvalidPassword,
    LegacyVaultDetected,
    MetadataCorrupted,
    UnsupportedFile,
    VaultError,
    VaultLocked,
    VaultNotFound,
    VaultUnlocked,
)
from vault import (
    delete_temporary_vault,
    lock_vault,
    recovery_pending,
    recover_temporary_vault,
    restore_backup_vault,
    unlock_vault,
    unlocked,
    vault_exists,
)
from file_import import import_files, validate_file_safety

BG = "#040607"
PANEL = "#0A0F10"
PANEL_2 = "#0E1516"
TEXT = "#DDF7EB"
MUTED = "#7CA59A"
ACCENT = "#25D8A0"
ACCENT_2 = "#1CA6BF"
ERROR = "#FF6B6B"
BORDER = "#16312D"
PROMPT = "vaultx>"

APP_WIDTH = 1040
APP_HEIGHT = 680

def configure_logging() -> None:
    """Configure timestamped logging to the VaultX log file."""

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
class PromptDialog(ctk.CTkToplevel):
    """Small modal prompt used for password-related input."""

    def __init__(
        self,
        master: ctk.CTk,
        title: str,
        label: str,
        *,
        confirm_label: str | None = None,
        show_confirm: bool = False,
    ) -> None:
        super().__init__(master)
        self.result: str | None = None
        self._show_confirm = show_confirm

        self.title(title)
        self.geometry("460x240")
        self.resizable(False, False)
        self.configure(fg_color=PANEL)
        self.transient(master)
        self.grab_set()

        self._font = ("Consolas", 13)

        container = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0)
        container.pack(fill="both", expand=True, padx=20, pady=20)

        title_label = ctk.CTkLabel(
            container,
            text=label,
            text_color=TEXT,
            font=("Consolas", 16, "bold"),
        )
        title_label.pack(anchor="w", pady=(0, 10))

        self.primary_entry = ctk.CTkEntry(
            container,
            height=36,
            fg_color=PANEL_2,
            border_color=BORDER,
            text_color=TEXT,
            font=self._font,
            show="•",
        )
        self.primary_entry.pack(fill="x", pady=(0, 12))
        self.primary_entry.focus_set()

        self.confirm_entry: ctk.CTkEntry | None = None
        if show_confirm:
            confirm_text = confirm_label or "Confirm Password"
            confirm_label_widget = ctk.CTkLabel(
                container,
                text=confirm_text,
                text_color=MUTED,
                font=("Consolas", 12),
            )
            confirm_label_widget.pack(anchor="w", pady=(0, 6))

            self.confirm_entry = ctk.CTkEntry(
                container,
                height=36,
                fg_color=PANEL_2,
                border_color=BORDER,
                text_color=TEXT,
                font=self._font,
                show="•",
            )
            self.confirm_entry.pack(fill="x", pady=(0, 12))

        self.error_label = ctk.CTkLabel(
            container,
            text="",
            text_color=ERROR,
            font=("Consolas", 12),
        )
        self.error_label.pack(anchor="w", pady=(0, 12))

        button_row = ctk.CTkFrame(container, fg_color=PANEL)
        button_row.pack(fill="x", pady=(4, 0))

        cancel_button = ctk.CTkButton(
            button_row,
            text="Cancel",
            fg_color="#1A2423",
            hover_color="#213230",
            text_color=TEXT,
            font=("Consolas", 12),
            width=110,
            command=self._cancel,
        )
        cancel_button.pack(side="right", padx=(10, 0))

        ok_button = ctk.CTkButton(
            button_row,
            text="OK",
            fg_color=ACCENT_2,
            hover_color=ACCENT,
            text_color="#00130D",
            font=("Consolas", 12, "bold"),
            width=110,
            command=self._submit,
        )
        ok_button.pack(side="right")

        self.bind("<Return>", lambda _event: self._submit())
        self.bind("<Escape>", lambda _event: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.wait_visibility()
        self.lift()
        self.focus_force()
        self.wait_window()

    def _cancel(self) -> None:
        self.result = None
        self.grab_release()
        self.destroy()

    def _submit(self) -> None:
        primary = self.primary_entry.get().strip()
        if not primary:
            self.error_label.configure(text="Password required.")
            return

        if self._show_confirm:
            confirm = self.confirm_entry.get().strip() if self.confirm_entry else ""
            if primary != confirm:
                self.error_label.configure(text=PASSWORDS_DO_NOT_MATCH)
                return

            if len(primary) < MIN_PASSWORD_LENGTH:
                self.error_label.configure(text=PASSWORD_TOO_SHORT)
                return

            self.result = primary
        else:
            self.result = primary

        self.grab_release()
        self.destroy()


class ProgressOverlay(ctk.CTkFrame):
    """Modal overlay displayed while backend operations run."""

    def __init__(self, master: ctk.CTk) -> None:
        super().__init__(master, fg_color="#020304", corner_radius=0)

        self.message_label = ctk.CTkLabel(
            self,
            text="",
            text_color=TEXT,
            font=("Consolas", 15),
        )
        self.message_label.pack(pady=(0, 14))

        self.progress_bar = ctk.CTkProgressBar(
            self,
            height=10,
            progress_color=ACCENT,
            border_color=BORDER,
        )
        self.progress_bar.pack(fill="x", padx=140)
        self.progress_bar.set(0)
        self.progress_bar.start()

    def set_message(self, text: str) -> None:
        """Update the overlay message."""

        self.message_label.configure(text=text)


class VaultXApp(ctk.CTk):
    """CustomTkinter desktop interface for VaultX."""

    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")

        super().__init__()
        self.title("VaultX")
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        self.minsize(900, 620)
        self.configure(fg_color=BG)

        self._session_password: str | None = None
        self._setup_password_visible = BooleanVar(value=False)
        self._current_view: ctk.CTkFrame | None = None
        self._overlay: ProgressOverlay | None = None
        self._busy = False
        self._startup_index = 0
        self._startup_lines = [
            "Initializing VaultX...",
            "Loading Argon2id + XChaCha20-Poly1305...",
            "Checking Vault...",
            "Ready.",
        ]
        self._mono_font = ("Consolas", 13)
        self._title_font = ("Consolas", 26, "bold")
        self._accent_font = ("Consolas", 13, "bold")

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(50, self._show_startup_screen)

    def run(self) -> None:
        """Start the application event loop."""

        self.mainloop()

    def _close(self) -> None:
        """Close the application cleanly."""

        self._clear_password_fields()
        self._session_password = None
        self.destroy()

    def _clear_view(self) -> None:
        """Remove the active view from the window."""

        if self._current_view is not None:
            self._current_view.destroy()
            self._current_view = None

    def _set_view(self, frame: ctk.CTkFrame) -> None:
        """Display the provided frame as the current screen."""

        self._clear_view()
        self._current_view = frame
        frame.pack(fill="both", expand=True)

    def _show_startup_screen(self) -> None:
        """Render the startup animation screen."""

        frame = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self._set_view(frame)

        shell = ctk.CTkFrame(
            frame,
            fg_color=PANEL,
            corner_radius=18,
            border_width=1,
            border_color=BORDER,
        )
        shell.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.66, relheight=0.5)

        title = ctk.CTkLabel(
            shell,
            text="VaultX",
            text_color=ACCENT,
            font=self._title_font,
        )
        title.pack(pady=(36, 8))

        subtitle = ctk.CTkLabel(
            shell,
            text="Secure terminal interface",
            text_color=MUTED,
            font=self._mono_font,
        )
        subtitle.pack(pady=(0, 22))

        self._startup_text = ctk.CTkLabel(
            shell,
            text=self._startup_lines[0],
            text_color=TEXT,
            font=self._mono_font,
        )
        self._startup_text.pack(pady=(0, 18))

        self._startup_bar = ctk.CTkProgressBar(shell, height=10, progress_color=ACCENT_2)
        self._startup_bar.pack(fill="x", padx=48)
        self._startup_bar.configure(mode="indeterminate")
        self._startup_bar.start()

        self._startup_hint = ctk.CTkLabel(
            shell,
            text="",
            text_color=MUTED,
            font=("Consolas", 11),
        )
        self._startup_hint.pack(pady=(20, 0))

        self._startup_index = 0
        self.after(500, self._advance_startup)

    def _advance_startup(self) -> None:
        """Advance the startup animation."""

        if self._startup_index < len(self._startup_lines):
            self._startup_text.configure(text=self._startup_lines[self._startup_index])
            self._startup_index += 1
            self.after(650, self._advance_startup)
            return

        self._startup_bar.stop()
        self._startup_hint.configure(text=STARTUP_MESSAGE % APP_VERSION)
        self.after(300, self._bootstrap_state)

    def _bootstrap_state(self) -> None:
        """Handle startup state and show the appropriate screen."""

        if is_legacy_vault():
            self._show_legacy_notice()
            return

        restore_backup_vault()

        if recovery_pending():
            self._show_recovery_dialog()

        # Check if vault file exists and is valid
        vault_file_exists = False
        if VAULT_CONTAINER_FILE.exists():
            try:
                # Try to read the vault file header to verify it's valid
                data = VAULT_CONTAINER_FILE.read_bytes()
                if len(data) >= 8 and data[:4] == b"VXDB":
                    vault_file_exists = True
            except Exception:
                pass

        if not vault_file_exists:
            self._show_welcome_screen()
            return

        if unlocked():
            self._show_terminal_screen()
            return

        if vault_exists():
            self._show_login_screen()
            return

        self._show_login_screen(error_message=NO_VAULT_FOUND)

    def _show_legacy_notice(self) -> None:
        """Render a migration notice when a legacy v2 vault is detected."""

        frame = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self._set_view(frame)

        card = ctk.CTkFrame(
            frame,
            fg_color=PANEL,
            corner_radius=18,
            border_width=1,
            border_color=BORDER,
        )
        card.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.60, relheight=0.58)

        title = ctk.CTkLabel(
            card,
            text="VaultX",
            text_color=ACCENT,
            font=("Consolas", 28, "bold"),
        )
        title.pack(pady=(32, 4))

        subtitle = ctk.CTkLabel(
            card,
            text="Legacy Vault Detected",
            text_color=ERROR,
            font=("Consolas", 18, "bold"),
        )
        subtitle.pack(pady=(0, 16))

        message = ctk.CTkLabel(
            card,
            text=LEGACY_VAULT_DETECTED,
            text_color=MUTED,
            font=("Consolas", 11),
            justify="center",
            wraplength=460,
        )
        message.pack(pady=(0, 24), padx=36)

        button = ctk.CTkButton(
            card,
            text="Create New Vault (fresh start)",
            fg_color=ACCENT_2,
            hover_color=ACCENT,
            text_color="#00130D",
            font=self._accent_font,
            height=40,
            command=self._show_welcome_screen,
        )
        button.pack(fill="x", padx=36)

    def _show_welcome_screen(self) -> None:
        """Render the first-time setup welcome screen."""

        frame = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self._set_view(frame)

        card = ctk.CTkFrame(
            frame,
            fg_color=PANEL,
            corner_radius=18,
            border_width=1,
            border_color=BORDER,
        )
        card.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.52, relheight=0.5)

        title = ctk.CTkLabel(
            card,
            text="VaultX",
            text_color=ACCENT,
            font=("Consolas", 28, "bold"),
        )
        title.pack(pady=(34, 4))

        subtitle = ctk.CTkLabel(
            card,
            text="Welcome",
            text_color=TEXT,
            font=("Consolas", 20, "bold"),
        )
        subtitle.pack(pady=(0, 16))

        message = ctk.CTkLabel(
            card,
            text="No encrypted vault was found.\n\nLet's create one.",
            text_color=MUTED,
            font=self._mono_font,
            justify="center",
        )
        message.pack(pady=(0, 24))

        button = ctk.CTkButton(
            card,
            text="Create Vault",
            fg_color=ACCENT_2,
            hover_color=ACCENT,
            text_color="#00130D",
            font=self._accent_font,
            height=40,
            command=self._show_setup_password_screen,
        )
        button.pack(fill="x", padx=36)

    def _show_setup_password_screen(self, error_message: str = "") -> None:
        """Render the first-time password creation screen."""

        frame = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self._set_view(frame)

        card = ctk.CTkFrame(
            frame,
            fg_color=PANEL,
            corner_radius=18,
            border_width=1,
            border_color=BORDER,
        )
        card.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.54, relheight=0.68)

        title = ctk.CTkLabel(
            card,
            text="VaultX",
            text_color=ACCENT,
            font=("Consolas", 28, "bold"),
        )
        title.pack(pady=(28, 4))

        subtitle = ctk.CTkLabel(
            card,
            text="Create Password",
            text_color=TEXT,
            font=("Consolas", 20, "bold"),
        )
        subtitle.pack(pady=(0, 12))

        self._setup_error = ctk.CTkLabel(
            card,
            text=error_message,
            text_color=ERROR if error_message else MUTED,
            font=("Consolas", 12),
        )
        self._setup_error.pack(anchor="w", padx=36, pady=(0, 6))

        master_label = ctk.CTkLabel(
            card,
            text="Master Password",
            text_color=MUTED,
            font=("Consolas", 12),
        )
        master_label.pack(anchor="w", padx=36, pady=(0, 6))

        self._setup_password_entry = ctk.CTkEntry(
            card,
            height=40,
            fg_color=PANEL_2,
            border_color=BORDER,
            text_color=TEXT,
            font=self._mono_font,
            show="•",
        )
        self._setup_password_entry.pack(fill="x", padx=36)

        confirm_label = ctk.CTkLabel(
            card,
            text="Confirm Password",
            text_color=MUTED,
            font=("Consolas", 12),
        )
        confirm_label.pack(anchor="w", padx=36, pady=(16, 6))

        self._setup_confirm_entry = ctk.CTkEntry(
            card,
            height=40,
            fg_color=PANEL_2,
            border_color=BORDER,
            text_color=TEXT,
            font=self._mono_font,
            show="•",
        )
        self._setup_confirm_entry.pack(fill="x", padx=36)

        toggle = ctk.CTkCheckBox(
            card,
            text="Show password",
            text_color=MUTED,
            font=("Consolas", 12),
            checkbox_width=18,
            checkbox_height=18,
            border_color=BORDER,
            fg_color=ACCENT_2,
            hover_color=ACCENT,
            command=self._toggle_setup_password_visibility,
            variable=self._setup_password_visible,
        )
        toggle.pack(anchor="w", padx=36, pady=(14, 10))

        button = ctk.CTkButton(
            card,
            text="Create Vault",
            fg_color=ACCENT_2,
            hover_color=ACCENT,
            text_color="#00130D",
            font=self._accent_font,
            height=40,
            command=self._submit_setup_password,
        )
        button.pack(fill="x", padx=36, pady=(8, 0))

        footer = ctk.CTkLabel(
            card,
            text="Minimum 8 characters. Press Enter to submit.",
            text_color=MUTED,
            font=("Consolas", 11),
        )
        footer.pack(pady=(14, 10))

        self._setup_password_entry.focus_set()
        self._setup_password_entry.bind("<Return>", lambda _event: self._submit_setup_password())
        self._setup_confirm_entry.bind("<Return>", lambda _event: self._submit_setup_password())
        self._toggle_setup_password_visibility()

    def _toggle_setup_password_visibility(self) -> None:
        """Show or hide the first-time setup password fields."""

        show_value = "" if self._setup_password_visible.get() else "•"
        if hasattr(self, "_setup_password_entry"):
            self._setup_password_entry.configure(show=show_value)
        if hasattr(self, "_setup_confirm_entry"):
            self._setup_confirm_entry.configure(show=show_value)

    def _submit_setup_password(self) -> None:
        """Validate the first-time password and create the vault config."""

        password = self._setup_password_entry.get().strip()
        confirm = self._setup_confirm_entry.get().strip()

        if len(password) < MIN_PASSWORD_LENGTH:
            self._setup_error.configure(
                text=f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
                text_color=ERROR,
            )
            return

        if password != confirm:
            self._setup_error.configure(text=PASSWORDS_DO_NOT_MATCH, text_color=ERROR)
            return

        self._run_backend_operation(
            status_text="Creating vault...",
            task=lambda: save_new_password(password),
            success_callback=lambda: self._on_setup_complete(password),
            error_callback=self._handle_setup_error,
        )

    def _on_setup_complete(self, password: str) -> None:
        """Store the new master password and show the completion screen."""

        self._session_password = password
        self._clear_password_fields()
        self._show_setup_complete_screen()

    def _clear_password_fields(self) -> None:
        """Clear password fields from memory after use."""

        for widget_name in ("_setup_password_entry", "_setup_confirm_entry", "_password_entry"):
            widget = getattr(self, widget_name, None)
            if widget is not None and hasattr(widget, "delete"):
                try:
                    if widget.winfo_exists():
                        widget.delete(0, "end")
                except Exception:
                    pass

    def _show_setup_complete_screen(self) -> None:
        """Render the setup completion screen."""

        frame = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self._set_view(frame)

        card = ctk.CTkFrame(
            frame,
            fg_color=PANEL,
            corner_radius=18,
            border_width=1,
            border_color=BORDER,
        )
        card.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.58, relheight=0.56)

        title = ctk.CTkLabel(
            card,
            text="VaultX",
            text_color=ACCENT,
            font=("Consolas", 28, "bold"),
        )
        title.pack(pady=(32, 4))

        subtitle = ctk.CTkLabel(
            card,
            text="Setup Complete",
            text_color=TEXT,
            font=("Consolas", 20, "bold"),
        )
        subtitle.pack(pady=(0, 16))

        message = ctk.CTkLabel(
            card,
            text="Your vault is ready.\n\nPlace any files you want to protect inside\n\nVault/\n\nWhen ready press",
            text_color=MUTED,
            font=self._mono_font,
            justify="center",
        )
        message.pack(pady=(0, 24))

        button = ctk.CTkButton(
            card,
            text="Lock Vault",
            fg_color=ACCENT_2,
            hover_color=ACCENT,
            text_color="#00130D",
            font=self._accent_font,
            height=40,
            command=self._lock_after_setup,
        )
        button.pack(fill="x", padx=36)

    def _lock_after_setup(self) -> None:
        """Lock the new vault and return to the login screen."""

        password = self._session_password
        if not password:
            self._show_login_screen()
            return

        self._run_backend_operation(
            status_text="Encrypting vault...",
            task=lambda: lock_vault(password),
            success_callback=self._on_lock_success,
            error_callback=self._handle_lock_error,
        )

    def _show_recovery_dialog(self) -> None:
        """Prompt the user to recover or delete a temporary file."""

        dialog = ctk.CTkToplevel(self)
        dialog.title("VaultX Recovery")
        dialog.geometry("440x220")
        dialog.resizable(False, False)
        dialog.configure(fg_color=PANEL)
        dialog.transient(self)
        dialog.grab_set()

        container = ctk.CTkFrame(dialog, fg_color=PANEL, corner_radius=0)
        container.pack(fill="both", expand=True, padx=20, pady=20)

        heading = ctk.CTkLabel(
            container,
            text=RECOVERY_MESSAGE,
            text_color=ACCENT,
            font=("Consolas", 18, "bold"),
        )
        heading.pack(anchor="w")

        message = ctk.CTkLabel(
            container,
            text="A temporary vault file was detected. Choose how to continue.",
            text_color=TEXT,
            font=self._mono_font,
            wraplength=380,
            justify="left",
        )
        message.pack(anchor="w", pady=(10, 18))

        def recover() -> None:
            try:
                recover_temporary_vault()
            except Exception as exc:  # noqa: BLE001 - keep startup recovery user-friendly
                logging.error("Recovery failed: %s", exc)
            finally:
                dialog.destroy()

        def delete_temp() -> None:
            delete_temporary_vault()
            dialog.destroy()

        button_row = ctk.CTkFrame(container, fg_color=PANEL)
        button_row.pack(fill="x", pady=(8, 0))

        delete_button = ctk.CTkButton(
            button_row,
            text="Delete temporary file",
            fg_color="#1A2423",
            hover_color="#213230",
            text_color=TEXT,
            font=("Consolas", 12),
            command=delete_temp,
        )
        delete_button.pack(side="right", padx=(10, 0))

        recover_button = ctk.CTkButton(
            button_row,
            text="Recover previous operation",
            fg_color=ACCENT_2,
            hover_color=ACCENT,
            text_color="#00130D",
            font=("Consolas", 12, "bold"),
            command=recover,
        )
        recover_button.pack(side="right")

        dialog.wait_window()

    def _show_login_screen(self, error_message: str = "") -> None:
        """Render the unlock login screen."""

        frame = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self._set_view(frame)

        card = ctk.CTkFrame(
            frame,
            fg_color=PANEL,
            corner_radius=18,
            border_width=1,
            border_color=BORDER,
        )
        card.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.5, relheight=0.56)

        title = ctk.CTkLabel(
            card,
            text="VaultX",
            text_color=ACCENT,
            font=("Consolas", 28, "bold"),
        )
        title.pack(pady=(34, 4))

        subtitle = ctk.CTkLabel(
            card,
            text="Master password required",
            text_color=MUTED,
            font=self._mono_font,
        )
        subtitle.pack(pady=(0, 22))

        self._login_error = ctk.CTkLabel(
            card,
            text=error_message,
            text_color=ERROR if error_message else MUTED,
            font=("Consolas", 12),
        )
        self._login_error.pack(anchor="w", padx=36, pady=(0, 8))

        self._password_entry = ctk.CTkEntry(
            card,
            height=40,
            fg_color=PANEL_2,
            border_color=BORDER,
            text_color=TEXT,
            font=self._mono_font,
            show="•",
            placeholder_text="Enter password",
        )
        self._password_entry.pack(fill="x", padx=36)
        self._password_entry.focus_set()
        self._password_entry.bind("<Return>", lambda _event: self._submit_login())

        button = ctk.CTkButton(
            card,
            text="Unlock",
            fg_color=ACCENT_2,
            hover_color=ACCENT,
            text_color="#00130D",
            font=self._accent_font,
            height=40,
            command=self._submit_login,
        )
        button.pack(fill="x", padx=36, pady=(18, 12))

        footer = ctk.CTkLabel(
            card,
            text="Press Enter to submit.",
            text_color=MUTED,
            font=("Consolas", 11),
        )
        footer.pack(pady=(0, 10))

    def _submit_login(self) -> None:
        """Unlock the vault using the login password."""

        password = self._password_entry.get().strip()
        if not password:
            self._login_error.configure(text="Invalid password.", text_color=ERROR)
            return

        self._run_backend_operation(
            status_text="Decrypting vault...",
            task=lambda: unlock_vault(password),
            success_callback=lambda: self._on_unlock_success(password),
            error_callback=self._handle_unlock_error,
        )

    def _handle_unlock_error(self, exc: Exception) -> None:
        """Display a login error after a failed unlock attempt."""

        if isinstance(exc, (InvalidPassword, CorruptedVault, MetadataCorrupted)):
            message = "Invalid password or corrupted vault."
        elif isinstance(exc, VaultNotFound):
            message = "No vault found."
        elif isinstance(exc, VaultUnlocked):
            message = "Vault is already unlocked."
        else:
            message = "Unable to unlock vault."

        self._login_error.configure(text=message, text_color=ERROR)
        self._show_login_screen(message)

    def _on_unlock_success(self, password: str) -> None:
        """Transition to the terminal after unlocking."""

        self._session_password = password
        self._clear_password_fields()
        self._show_terminal_screen()

    def _show_terminal_screen(self) -> None:
        """Render the command terminal screen."""

        frame = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self._set_view(frame)

        header = ctk.CTkFrame(
            frame,
            fg_color=PANEL,
            corner_radius=16,
            border_width=1,
            border_color=BORDER,
        )
        header.pack(fill="x", padx=24, pady=(22, 12))

        left = ctk.CTkFrame(header, fg_color=PANEL)
        left.pack(side="left", padx=22, pady=16)

        title = ctk.CTkLabel(
            left,
            text="VaultX Terminal",
            text_color=ACCENT,
            font=("Consolas", 24, "bold"),
        )
        title.pack(anchor="w")

        self._terminal_status = ctk.CTkLabel(
            left,
            text=self._status_text(),
            text_color=MUTED,
            font=self._mono_font,
        )
        self._terminal_status.pack(anchor="w", pady=(6, 0))

        right = ctk.CTkLabel(
            header,
            text=f"{VAULT_CONTAINER_FILE.parent}",
            text_color=TEXT,
            font=("Consolas", 11),
        )
        right.pack(side="right", padx=22, pady=18)

        terminal_shell = ctk.CTkFrame(
            frame,
            fg_color=PANEL,
            corner_radius=16,
            border_width=1,
            border_color=BORDER,
        )
        terminal_shell.pack(fill="both", expand=True, padx=24, pady=(0, 18))

        self._terminal_output = ctk.CTkTextbox(
            terminal_shell,
            fg_color=BG,
            text_color=TEXT,
            border_color=BORDER,
            corner_radius=12,
            font=self._mono_font,
            wrap="word",
        )
        self._terminal_output.pack(fill="both", expand=True, padx=16, pady=(16, 12))
        self._terminal_output.configure(state="normal")
        self._terminal_output.delete("1.0", "end")
        self._print_terminal_banner()
        self._terminal_output.configure(state="disabled")

        prompt_row = ctk.CTkFrame(terminal_shell, fg_color=PANEL)
        prompt_row.pack(fill="x", padx=16, pady=(0, 16))

        prompt_label = ctk.CTkLabel(
            prompt_row,
            text=PROMPT,
            text_color=ACCENT,
            font=("Consolas", 13, "bold"),
            width=84,
        )
        prompt_label.pack(side="left", padx=(0, 10))

        self._command_entry = ctk.CTkEntry(
            prompt_row,
            height=38,
            fg_color=PANEL_2,
            border_color=BORDER,
            text_color=TEXT,
            font=self._mono_font,
            placeholder_text="Type help for commands",
        )
        self._command_entry.pack(side="left", fill="x", expand=True)
        self._command_entry.focus_set()
        self._command_entry.bind("<Return>", lambda _event: self._submit_command())

        self._append_terminal_line("")
        self._append_terminal_line("Type help for available commands.")
        self._append_terminal_line("")

    def _print_terminal_banner(self) -> None:
        """Print the initial terminal banner."""

        self._append_terminal_line("VaultX secure terminal")
        self._append_terminal_line(self._status_text())
        self._append_terminal_line("")
        self._append_terminal_line("Ready for commands.")
        self._append_terminal_line("")

    def _status_text(self) -> str:
        """Return a concise vault status string."""

        if unlocked():
            return "Status: Vault unlocked"
        if vault_exists():
            return "Status: Vault locked"
        return "Status: No vault detected"

    def _append_terminal_line(self, text: str) -> None:
        """Append a line to the terminal output."""

        self._terminal_output.configure(state="normal")
        if text:
            self._terminal_output.insert("end", f"{text}\n")
        else:
            self._terminal_output.insert("end", "\n")
        self._terminal_output.see("end")
        self._terminal_output.configure(state="disabled")

    def _clear_terminal(self) -> None:
        """Clear the terminal history."""

        self._terminal_output.configure(state="normal")
        self._terminal_output.delete("1.0", "end")
        self._terminal_output.configure(state="disabled")

    def _submit_command(self) -> None:
        """Process the entered terminal command."""

        command = self._command_entry.get().strip()
        self._command_entry.delete(0, "end")

        if not command:
            return

        self._append_terminal_line(f"{PROMPT} {command}")

        command_name = command.lower()
        if command_name == "help":
            self._append_terminal_help()
            return

        if command_name == "status":
            self._append_terminal_line(self._status_text())
            return

        if command_name == "clear":
            self._clear_terminal()
            return

        if command_name == "open":
            self._open_vault_folder()
            return

        if command_name == "lock":
            self._request_lock()
            return

        if command_name == "passwd":
            self._request_password_change()
            return

        if command_name == "import":
            self._request_file_import()
            return

        if command_name == "exit":
            self._close()
            return

        self._append_terminal_line("Unknown command. Type help.")

    def _append_terminal_help(self) -> None:
        """Print available terminal commands."""

        self._append_terminal_line("Commands:")
        self._append_terminal_line("  open   Open the Vault folder")
        self._append_terminal_line("  lock   Lock the vault")
        self._append_terminal_line("  status Show vault status")
        self._append_terminal_line("  passwd Change the master password")
        self._append_terminal_line("  import Add files to vault")
        self._append_terminal_line("  help   Show this help")
        self._append_terminal_line("  clear  Clear the terminal")
        self._append_terminal_line("  exit   Close VaultX")

    def _open_vault_folder(self) -> None:
        """Open the vault folder in the system file explorer."""

        if not VAULT_DIR.exists():
            self._append_terminal_line(VAULT_FOLDER_NOT_FOUND)
            return

        try:
            os.startfile(str(VAULT_DIR))
            self._append_terminal_line(f"Opened {VAULT_DIR}.")
        except OSError as exc:
            logging.error("Failed to open vault folder: %s", exc)
            self._append_terminal_line("Unable to open the Vault folder.")

    def _request_lock(self) -> None:
        """Lock the vault using the current session password or a prompt."""

        password = self._session_password
        if password is None:
            prompt = PromptDialog(
                self,
                title="Lock Vault",
                label="Enter master password",
            )
            password = prompt.result if isinstance(prompt.result, str) else None
            if not password:
                self._append_terminal_line("Lock cancelled.")
                return

        self._run_backend_operation(
            status_text="Encrypting vault...",
            task=lambda: lock_vault(password),
            success_callback=self._on_lock_success,
            error_callback=self._handle_lock_error,
        )

    def _on_lock_success(self) -> None:
        """Return to the login screen after a successful lock."""

        self._clear_password_fields()
        self._session_password = None
        self._show_login_screen()

    def _handle_setup_error(self, exc: Exception) -> None:
        """Display a setup error and keep the wizard active."""

        if isinstance(exc, VaultError):
            message = str(exc)
        else:
            message = VAULT_CREATION_FAILED

        self._show_setup_password_screen(message)

    def _handle_lock_error(self, exc: Exception) -> None:
        """Display a lock error message."""

        if isinstance(exc, (VaultLocked, VaultNotFound, CorruptedVault, FileTooLarge)):
            message = str(exc)
        elif isinstance(exc, UnsupportedFile):
            message = str(exc)
        else:
            message = "Unable to lock vault."

        self._append_terminal_line(message)
        self._show_terminal_screen()

    def _request_password_change(self) -> None:
        """Ask for a new master password and re-encrypt the vault."""

        dialog = PromptDialog(
            self,
            title="Change Password",
            label="Enter new password",
            confirm_label="Confirm new password",
            show_confirm=True,
        )
        if not isinstance(dialog.result, str):
            self._append_terminal_line("Password change cancelled.")
            return

        new_password = dialog.result
        self._run_backend_operation(
            status_text="Updating password...",
            task=lambda: self._change_password(new_password),
            success_callback=lambda: self._append_terminal_line("Password updated."),
            error_callback=self._handle_password_change_error,
        )

    def _change_password(self, new_password: str) -> None:
        """Change the vault password without re-encrypting files (v4 instant change)."""
        from password_manager import PasswordManager

        # Prompt for current password to verify identity
        dialog = PromptDialog(
            self,
            title="Verify Password",
            label="Enter current password",
            show_confirm=False,
        )
        if not isinstance(dialog.result, str):
            raise ValueError("Password change cancelled")

        old_password = dialog.result

        # Perform instant password change (no file re-encryption needed)
        pm = PasswordManager(VAULT_CONTAINER_FILE)
        if not pm.change_password(old_password, new_password):
            raise ValueError("Current password is incorrect")

    def _handle_password_change_error(self, exc: Exception) -> None:
        """Report password update failures."""

        if isinstance(exc, VaultError):
            self._append_terminal_line(str(exc))
        else:
            self._append_terminal_line("Unable to change password.")

        if unlocked():
            self._show_terminal_screen()
        else:
            self._show_login_screen(error_message="Password updated. Unlock with the new password.")

    def _request_file_import(self) -> None:
        """Prompt for file path and import to vault."""

        dialog = ctk.CTkToplevel(self)
        dialog.title("Import Files to Vault")
        dialog.geometry("500x280")
        dialog.resizable(False, False)
        dialog.configure(fg_color=PANEL)
        dialog.transient(self)
        dialog.grab_set()

        container = ctk.CTkFrame(dialog, fg_color=PANEL, corner_radius=0)
        container.pack(fill="both", expand=True, padx=20, pady=20)

        title = ctk.CTkLabel(
            container,
            text="Import Files to Vault",
            text_color=ACCENT,
            font=("Consolas", 16, "bold"),
        )
        title.pack(anchor="w", pady=(0, 10))

        info = ctk.CTkLabel(
            container,
            text="Enter the full path to a file or folder to add to your vault.",
            text_color=MUTED,
            font=("Consolas", 11),
            wraplength=420,
            justify="left",
        )
        info.pack(anchor="w", pady=(0, 12))

        label = ctk.CTkLabel(
            container,
            text="File/Folder Path",
            text_color=MUTED,
            font=("Consolas", 11),
        )
        label.pack(anchor="w", pady=(0, 6))

        path_entry = ctk.CTkEntry(
            container,
            height=36,
            fg_color=PANEL_2,
            border_color=BORDER,
            text_color=TEXT,
            font=("Consolas", 11),
        )
        path_entry.pack(fill="x", pady=(0, 14))
        path_entry.focus_set()

        error_label = ctk.CTkLabel(
            container,
            text="",
            text_color=ERROR,
            font=("Consolas", 10),
        )
        error_label.pack(anchor="w", pady=(0, 12))

        def import_file() -> None:
            file_path = path_entry.get().strip()
            if not file_path:
                error_label.configure(text="Please enter a file or folder path.", text_color=ERROR)
                return

            is_safe, reason = validate_file_safety(file_path)
            if not is_safe:
                error_label.configure(text=f"Invalid: {reason}", text_color=ERROR)
                return

            dialog.destroy()

            if not self._session_password:
                self._append_terminal_line("Session expired. Please unlock the vault again before importing.")
                return

            def _on_import_error(exc: Exception) -> None:
                if isinstance(exc, FileTooLarge):
                    self._append_terminal_line(f"Import blocked: {exc}")
                elif isinstance(exc, UnsupportedFile):
                    self._append_terminal_line(f"Import blocked: {exc}")
                elif isinstance(exc, InvalidPassword):
                    self._append_terminal_line("Import failed: invalid password.")
                else:
                    self._append_terminal_line(f"Import failed: {exc}")

            self._run_backend_operation(
                status_text="Importing files...",
                task=lambda: import_files([file_path], self._session_password),
                success_callback=lambda: self._append_terminal_line("Files imported successfully."),
                error_callback=_on_import_error,
            )

        button_row = ctk.CTkFrame(container, fg_color=PANEL)
        button_row.pack(fill="x", pady=(4, 0))

        cancel_button = ctk.CTkButton(
            button_row,
            text="Cancel",
            fg_color="#1A2423",
            hover_color="#213230",
            text_color=TEXT,
            font=("Consolas", 11),
            width=110,
            command=dialog.destroy,
        )
        cancel_button.pack(side="right", padx=(10, 0))

        import_button = ctk.CTkButton(
            button_row,
            text="Import",
            fg_color=ACCENT_2,
            hover_color=ACCENT,
            text_color="#00130D",
            font=("Consolas", 11, "bold"),
            width=110,
            command=import_file,
        )
        import_button.pack(side="right")

        path_entry.bind("<Return>", lambda _event: import_file())
        dialog.wait_window()

    def _run_backend_operation(
        self,
        *,
        status_text: str,
        task: Callable[[], None],
        success_callback: Callable[[], None],
        error_callback: Callable[[Exception], None],
    ) -> None:
        """Run a backend operation with a progress overlay."""

        if self._busy:
            return

        self._busy = True
        self._show_overlay(status_text)

        result_queue: queue.Queue[tuple[bool, Exception | None]] = queue.Queue()

        def worker() -> None:
            try:
                task()
            except Exception as exc:  # noqa: BLE001 - backend must surface the error
                result_queue.put((False, exc))
            else:
                result_queue.put((True, None))

        threading.Thread(target=worker, daemon=True).start()
        self.after(80, lambda: self._poll_operation(result_queue, success_callback, error_callback))

    def _poll_operation(
        self,
        result_queue: queue.Queue[tuple[bool, Exception | None]],
        success_callback: Callable[[], None],
        error_callback: Callable[[Exception], None],
    ) -> None:
        """Poll the completion queue for a backend task."""

        if result_queue.empty():
            self.after(80, lambda: self._poll_operation(result_queue, success_callback, error_callback))
            return

        success, error = result_queue.get()
        self._hide_overlay()
        self._busy = False

        if success:
            success_callback()
            return

        assert error is not None
        error_callback(error)

    def _show_overlay(self, message: str) -> None:
        """Display the progress overlay."""

        if self._overlay is not None:
            self._overlay.destroy()

        self._overlay = ProgressOverlay(self)
        self._overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._overlay.lift()
        self._overlay.set_message(message)
        self._disable_inputs(True)

    def _hide_overlay(self) -> None:
        """Remove the progress overlay."""

        self._disable_inputs(False)
        if self._overlay is not None:
            self._overlay.destroy()
            self._overlay = None

    def _disable_inputs(self, disabled: bool) -> None:
        """Enable or disable interactive widgets."""

        state = "disabled" if disabled else "normal"

        for widget_name in (
            "_password_entry",
            "_command_entry",
            "_setup_password_entry",
            "_setup_confirm_entry",
        ):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                try:
                    if not widget.winfo_exists():
                        setattr(self, widget_name, None)
                        continue
                    widget.configure(state=state)
                except TclError:
                    setattr(self, widget_name, None)

    def _handle_recovery_exception(self, exc: Exception) -> None:
        """Show a safe error message when recovery fails."""

        logging.error("Recovery failure: %s", exc)
        self._show_login_screen(error_message=TEMP_FILE_MISSING)


def run() -> None:
    """Start the VaultX desktop application."""

    configure_logging()
    logging.info(STARTUP_MESSAGE, APP_VERSION)
    app = VaultXApp()
    try:
        app.run()
    except KeyboardInterrupt:
        logging.info(OPERATION_CANCELLED)
    finally:
        logging.info(SHUTDOWN_MESSAGE)
