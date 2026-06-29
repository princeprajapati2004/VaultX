# VaultX - Secure File Encryption & Storage

A secure desktop application for encrypting and protecting personal files and data with password-protected access.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture & Workflow](#architecture--workflow)
3. [Security Features](#security-features)
4. [Algorithms & Functions](#algorithms--functions)
5. [Command Reference](#command-reference)
6. [Building .EXE](#building-exe)
7. [Context Menu Integration](#context-menu-integration)
8. [Advanced Features](#advanced-features)

---

## Quick Start

### Installation

```bash
# Clone or extract the project
cd C:\FCT\VaultX

# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

### First Launch

1. **Create Vault** - Set a strong master password (minimum 8 characters)
2. **Add Files** - Place files in the `Vault/` folder or use the `import` command
3. **Lock Vault** - Encrypts and protects all files
4. **Unlock** - Enter password to decrypt and access files

---

## Architecture & Workflow

### Current Application Flow

```
┌─────────────────────────────────────────────────────────────┐
│ VaultX Startup                                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ 1. Check if config.json exists (password setup status)      │
│ 2. Check if vault.dat exists (encrypted vault)             │
│ 3. Check if Vault/ folder exists (currently unlocked)      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                            ↓
                    ┌───────┴───────┐
                    │               │
            ┌───────▼────────┐  ┌──▼─────────────┐
            │ No Config      │  │ Has Config     │
            │ First Run      │  │ Existing User  │
            └────────────────┘  └────────────────┘
                    ↓                   ↓
            ┌────────────────┐  ┌──────────────────┐
            │ Welcome Screen │  │ Check Vault State│
            │ Create Password│  └──────────────────┘
            └────────────────┘          ↓
                    │      ┌────────────┼────────────┐
                    │      │            │            │
                    ↓      ▼            ▼            ▼
              ┌─────────┐┌────────┐┌─────────┐┌──────────┐
              │ Create  ││Unlock  ││Terminal ││Locked    │
              │ Vault   ││Screen  ││(Active) ││(Locked)  │
              └─────────┘└────────┘└─────────┘└──────────┘
```

### State Management

| State | Condition | Action |
|-------|-----------|--------|
| **NO_CONFIG** | `config.json` doesn't exist | Show welcome screen, create password |
| **SETUP** | `config.json` exists, `vault.dat` doesn't | Show setup complete, ready to lock |
| **LOCKED** | `vault.dat` exists, `Vault/` doesn't | Show login screen, unlock with password |
| **UNLOCKED** | `vault.dat` exists, `Vault/` exists | Show terminal, allow file management |

### Directory Structure

```
C:\FCT\VaultX/
├── main.py                    # Entry point
├── ui.py                      # CustomTkinter GUI
├── vault.py                   # Lock/unlock logic
├── crypto.py                  # Encryption/decryption
├── config.py                  # Password verification
├── archive.py                 # ZIP compression/extraction
├── file_import.py             # File import handler
├── context_menu_setup.py      # Windows registry integration
├── constants.py               # Configuration constants
├── exceptions.py              # Custom exceptions
├── data/
│   ├── config.json           # Password hash, salt, iterations
│   ├── vault.dat             # Encrypted vault (ZIP bytes)
│   ├── vault.tmp             # Temporary during lock/unlock
│   └── vault.bak             # Backup during operations
├── Vault/                     # Unlocked folder (plaintext files)
├── logs/
│   └── vault.log             # Application log file
└── .venv/                     # Python virtual environment
```

---

## Security Features

### 1. Password Security

- **Algorithm:** PBKDF2-HMAC-SHA256
- **Iterations:** 600,000 (NIST-recommended)
- **Salt Length:** 128 bits (16 bytes)
- **Verification:** Constant-time comparison using `secrets.compare_digest()`
- **Protection:** Password verified BEFORE decryption attempt

**Flow:**
```
User Input → PBKDF2(password, salt, 600k) → Compare with stored hash
                                                    ↓
                                          Hash Match? → Proceed to decrypt
                                                    ↓
                                          Hash Mismatch? → Reject + Rate limit
```

### 2. Encryption

- **Algorithm:** Fernet (AES-128-CBC with HMAC authentication)
- **Key Derivation:** Same PBKDF2 hash, base64-encoded for Fernet
- **Integrity:** Built-in HMAC-SHA256 verification
- **Ciphertext Authentication:** InvalidToken exception on tampering

### 3. Archive Security

- **Compression:** ZIP with DEFLATE (standard compression, not encryption)
- **Path Validation:** Prevents ZIP slip attacks (directory traversal)
- **Symlink Detection:** Rejects symbolic links to prevent bypass

### 4. Rate Limiting

- **Failed Attempts:** After 5 failed unlock attempts
- **Lockout Duration:** 5 seconds (prevents brute force)
- **Reset:** Automatic on successful unlock

**Attack Prevention:**
```
1st attempt: Fail → tracked
2nd-4th:    Fail → tracked
5th attempt: Fail → LOCKED for 5 seconds
6th attempt: Before 5s → "Try again in Xs"
             After 5s  → Counter reset, allow retry
```

### 5. Memory Security

- **Plaintext Clearing:** Password fields cleared immediately after use
- **Session Management:** Password zeroized on exit/lock
- **Widget Cleanup:** UI text fields emptied after authentication

---

## Algorithms & Functions

### Core Encryption Module (`crypto.py`)

#### `generate_key(password: str, salt: str) -> bytes`
```python
# Purpose: Derive Fernet encryption key from password
# Input:   password (plaintext), salt (hex string)
# Output:  base64-encoded 32-byte key for Fernet
# Algorithm:
#   1. Decode salt from hex to bytes
#   2. Apply PBKDF2-HMAC-SHA256:
#      - Hash function: SHA256
#      - Iterations: 600,000
#      - Output length: 32 bytes
#   3. Base64-encode result for Fernet compatibility
```

#### `encrypt_bytes(data: bytes, password: str, salt: str) -> bytes`
```python
# Purpose: Encrypt data with password-derived key
# Input:   data (plaintext bytes), password, salt
# Output:  Fernet encrypted bytes (includes IV + ciphertext + HMAC)
# Process:
#   1. Generate key using generate_key()
#   2. Create Fernet cipher with key
#   3. Encrypt data (Fernet adds IV + HMAC automatically)
```

#### `decrypt_bytes(data: bytes, password: str, salt: str) -> bytes`
```python
# Purpose: Decrypt Fernet-encrypted data
# Input:   data (encrypted bytes), password, salt
# Output:  plaintext bytes (or raises InvalidToken on tampering)
# Process:
#   1. Generate key using generate_key()
#   2. Verify HMAC (Fernet automatically)
#   3. Decrypt using AES-128-CBC
#   4. Return plaintext
```

### Configuration Module (`config.py`)

#### `derive_key(password: str, salt: str) -> str`
```python
# Purpose: Create password hash for verification
# Input:   password (plaintext), salt (hex string)
# Output:  hex-encoded password hash
# Algorithm:
#   1. Convert password to UTF-8 bytes
#   2. Convert salt from hex string to bytes
#   3. Apply PBKDF2-HMAC-SHA256 (600,000 iterations)
#   4. Output length: 32 bytes
#   5. Return as hex string for storage in JSON
```

#### `verify_password(password: str) -> bool`
```python
# Purpose: Authenticate user password against stored hash
# Input:   password (plaintext)
# Output:  True if password matches, False otherwise
# Process:
#   1. Load config.json (contains stored_hash and salt)
#   2. Derive hash from user input: derive_key(password, salt)
#   3. Compare using secrets.compare_digest() - CONSTANT TIME
#   4. Timing-safe comparison prevents timing attacks
#   5. Return result
```

#### `save_new_password(password: str) -> None`
```python
# Purpose: Store password hash on vault creation
# Process:
#   1. Generate 128-bit cryptographic random salt (16 bytes hex)
#   2. Derive password hash: derive_key(password, salt)
#   3. Create config.json with:
#      {
#        "version": 1,
#        "iterations": 600000,
#        "salt": "hex_salt_here",
#        "password_hash": "hex_hash_here"
#      }
#   4. No plaintext password is stored
```

### Vault Module (`vault.py`)

#### `lock_vault(password: str) -> None`
```python
# Purpose: Encrypt and compress the unlocked Vault/ folder
# Security Checks:
#   1. Verify VAULT_DIR exists (folder to lock)
#   2. Create backup of existing vault.dat if present
#   3. Verify password hash (since v2.1)
# Process:
#   1. Compress Vault/ → ZIP bytes in memory
#   2. Encrypt ZIP bytes with Fernet (password-derived key)
#   3. Write to vault.tmp (atomic operation safety)
#   4. Verify encryption by decrypting vault.tmp
#   5. Atomic move: vault.tmp → vault.dat
#   6. Delete Vault/ folder (no plaintext remains)
#   7. Clean up backup on success
# Failure Handling:
#   - If encryption fails: restore from backup
#   - If decryption fails: restore from backup
#   - Never leaves corrupted state
```

#### `unlock_vault(password: str) -> None`
```python
# Purpose: Decrypt vault and restore Vault/ folder
# Security Checks:
#   1. Check rate limit (5 attempts → 5s lockout)
#   2. Verify password hash - MUST PASS BEFORE DECRYPTION
#   3. Decrypt vault.dat with password-derived key
#   4. Validate ZIP integrity after decryption
#   5. Validate all extracted paths (ZIP slip prevention)
# Process:
#   1. Load encrypted vault.dat
#   2. Decrypt using Fernet (password-derived key)
#   3. Validate decrypted data is valid ZIP
#   4. Extract ZIP → Vault/ folder (with path validation)
#   5. Reset rate limit on success
# Error Handling:
#   - InvalidToken → wrong password
#   - CorruptedVault → zip invalid or extraction failed
#   - Rate limit triggered → reject attempt
```

#### Rate Limiting Functions

```python
def _check_rate_limit(attempt_key: str = "unlock") -> None:
    """
    Enforce rate limiting on failed authentication.
    
    State Tracking:
      _FAILED_ATTEMPTS = {
        "unlock": (timestamp, attempt_count)
      }
    
    Logic:
      - If count >= 5 AND elapsed < 5 seconds:
          Raise InvalidPassword("Too many attempts. Try again in Xs")
      - If count >= 5 AND elapsed >= 5 seconds:
          Reset counter to 0
      - Increment attempt counter
    """

def _reset_rate_limit(attempt_key: str = "unlock") -> None:
    """Clear rate limit tracking on successful authentication."""
```

### Archive Module (`archive.py`)

#### `folder_to_bytes(folder_path: str | Path) -> bytes`
```python
# Purpose: Compress folder into ZIP bytes
# Input:   Path to Vault/ folder
# Output:  ZIP file bytes in memory
# Process:
#   1. Create in-memory BytesIO buffer
#   2. Create ZipFile with ZIP_DEFLATED compression
#   3. Recursively add all files from folder
#   4. Store paths relative to source folder
#   5. Close ZIP and return bytes
# Compression: DEFLATE (not encryption, just compression)
```

#### `bytes_to_folder(data: bytes, output_folder: str | Path) -> None`
```python
# Purpose: Extract ZIP bytes into folder with security validation
# Input:   ZIP bytes, destination folder path
# Security Validation:
#   1. Resolve both paths to absolute paths
#   2. For each member in ZIP:
#      - Resolve final path: output_path / member_name
#      - Check resolved path starts with output_path
#      - Reject if path starts with .. or ~
#      - Reject if path is absolute
# Process:
#   1. Validate member path (prevents ZIP slip)
#   2. Extract individual member to output_folder
#   3. Raises ValueError if path traversal detected
# ZIP Slip Prevention:
#   - Blocks: ../../../etc/passwd
#   - Blocks: C:\Windows\System32\file.txt
#   - Blocks: ~/sensitive/data
#   - Allows: normal/relative/paths
```

#### `is_valid_zip_bytes(data: bytes) -> bool`
```python
# Purpose: Verify ZIP integrity
# Process:
#   1. Open ZIP in read mode
#   2. Run testzip() method (verifies all CRCs)
#   3. Return True if all files valid
#   4. Return False if BadZipFile or CRC error
```

### File Import Module (`file_import.py`)

#### `import_files(file_paths: list[str], password: str) -> None`
```python
# Purpose: Import files into unlocked vault with password verification
# Security:
#   1. Verify password against stored hash (same as unlock)
#   2. Check vault is unlocked (Vault/ folder exists)
#   3. Validate each file for safety before import
# Process:
#   1. For each file/folder in file_paths:
#      - Call validate_file_safety()
#      - If file: copy to Vault/ with unique naming
#      - If directory: copy tree to Vault/
# Conflict Handling:
#   - If file exists: rename with counter (file_1, file_2, etc.)
#   - Preserves timestamps and permissions
```

#### `validate_file_safety(file_path: str) -> tuple[bool, str]`
```python
# Purpose: Security check before importing
# Validations:
#   1. File exists
#   2. Not a symbolic link (prevents bypass)
#   3. File size <= 5GB
#   4. Not executable: .exe, .dll, .sys, .bat, .cmd, .ps1
# Returns: (is_safe: bool, reason: str)
```

---

## Command Reference

### Terminal Commands (when vault is unlocked)

| Command | Description | Example |
|---------|-------------|---------|
| `open` | Open Vault folder in file explorer | `open` |
| `lock` | Encrypt and lock the vault | `lock` |
| `import` | Add files/folders to vault | `import` |
| `passwd` | Change master password | `passwd` |
| `status` | Show vault lock/unlock status | `status` |
| `help` | Display all commands | `help` |
| `clear` | Clear terminal history | `clear` |
| `exit` | Close VaultX | `exit` |

### File Import Flow

```
User types: "import"
    ↓
Dialog box appears: "Enter file/folder path"
    ↓
User enters: "C:\Users\Documents\SecretFile.txt"
    ↓
Validation checks:
  - File exists? ✓
  - Executable? ✗
  - Size < 5GB? ✓
    ↓
Import starts (with progress overlay)
    ↓
File copied to Vault/SecretFile.txt
    ↓
Success message: "Files imported successfully."
```

---

## Building .EXE

### Prerequisites

```bash
# Install PyInstaller
pip install pyinstaller

# Verify installation
pyinstaller --version
```

### Build Steps

#### Step 1: Create Build Script

Create `build_exe.bat` in project root:

```batch
@echo off
REM Build VaultX.exe
echo Building VaultX...

REM Clean previous builds
if exist "dist\" rmdir /s /q dist
if exist "build\" rmdir /s /q build
if exist "*.spec" del *.spec

REM Build executable
pyinstaller --onefile ^
  --windowed ^
  --name VaultX ^
  --icon=icon.ico ^
  --add-data "data:data" ^
  --distpath ".\dist" ^
  --buildpath ".\build" ^
  main.py

echo Build complete! VaultX.exe is in dist\ folder
pause
```

#### Step 2: Prepare Assets

1. **Create icon** (optional but recommended):
   - Convert an image to `icon.ico`
   - Place in project root

2. **Verify data directory**:
   ```
   C:\FCT\VaultX\data\
   └── config.json  (will be created on first run)
   ```

#### Step 3: Run Build

```bash
# Option 1: Run batch file
build_exe.bat

# Option 2: Direct PyInstaller command
pyinstaller --onefile --windowed --name VaultX --icon=icon.ico --add-data "data:data" main.py
```

#### Step 4: Output

```
dist/
└── VaultX.exe  (Single executable file, no dependencies needed)
```

### Distribution

After building, you only need to distribute:

1. **VaultX.exe** - Single file executable
2. **README.md** - User documentation
3. **LICENSE** - License file (if applicable)

Users can run `VaultX.exe` on Windows without installing Python or dependencies.

### Build Optimization

For smaller executable:

```batch
pyinstaller --onefile --windowed --name VaultX ^
  --add-data "data:data" ^
  --exclude-module matplotlib ^
  --exclude-module numpy ^
  --exclude-module scipy ^
  main.py
```

---

## Context Menu Integration

### For Users with .EXE

#### Step 1: Run Registry Setup (One-time only)

```bash
# Run with Administrator privileges
python context_menu_setup.py --register "C:\path\to\VaultX.exe"
```

Or create a `register_context_menu.bat`:

```batch
@echo off
REM Run as Administrator
python context_menu_setup.py --register "%~dp0VaultX.exe"
echo VaultX context menu registered!
pause
```

#### Step 2: Verify Registration

```bash
python context_menu_setup.py --check
```

Output: `VaultX context menu is registered`

#### Step 3: Use Context Menu

1. Right-click any file or folder
2. Select **"Add to VaultX"**
3. VaultX launches with import prompt
4. Enter password when prompted
5. File is securely added to vault

### Unregister Context Menu

```bash
# Remove context menu integration
python context_menu_setup.py --unregister
```

### Registry Entries Added

```
HKEY_CLASSES_ROOT
├── *\shell\AddToVaultX
│   └── command → "VaultX.exe --import "%1""
│
└── Directory\shell\AddToVaultX
    └── command → "VaultX.exe --import "%1""
```

### What Registry Does

- **Files:** `Right-click → "Add to VaultX"` → `VaultX.exe --import "path"`
- **Folders:** `Right-click → "Add to VaultX"` → `VaultX.exe --import "path"`
- **Portable:** Settings stored in Windows registry, can be removed completely

---

## Advanced Features

### Password Change Flow

```
User selects: "passwd"
    ↓
Dialog: "Enter new password" (minimum 8 chars)
    ↓
Dialog: "Confirm new password"
    ↓
Backend Process:
  1. Backup old config.json
  2. Generate new salt
  3. Create new password_hash
  4. Save to config.json
  5. Lock vault with new password
  6. Unlock vault to verify
  7. Delete backup
    ↓
Success message: "Password updated."
```

### Vault Recovery

If application crashes during lock/unlock:

```
1. Temporary file vault.tmp exists
2. On next startup:
   - VaultX detects vault.tmp
   - Shows recovery dialog
   - Option 1: "Recover previous operation"
   - Option 2: "Delete temporary file"
```

### Logging

All operations logged to `logs/vault.log`:

```
2026-06-29 10:15:23 INFO Vault unlocked.
2026-06-29 10:16:45 INFO Creating archive.
2026-06-29 10:16:47 INFO Encrypting.
2026-06-29 10:16:48 INFO Vault locked.
2026-06-29 10:17:12 INFO Password updated.
```

### Configuration File Format

**`data/config.json`:**

```json
{
    "version": 1,
    "iterations": 600000,
    "salt": "4db2063cb45285bd861222289410d63c",
    "password_hash": "bc95b9ad76417688c43da264c14cbee72c29816707f2c64d4012da6d54449663"
}
```

| Field | Purpose | Details |
|-------|---------|---------|
| `version` | Config format version | For future compatibility |
| `iterations` | PBKDF2 iteration count | NIST recommendation: 600,000+ |
| `salt` | Cryptographic salt (hex) | 128 bits, unique per installation |
| `password_hash` | Stored password hash | Never transmitted, local verification only |

---

## Troubleshooting

### Password Incorrect After Correct Entry

- Passwords are case-sensitive
- No spaces are trimmed from beginning/end of password
- CAPSLOCK affects password

### Context Menu Not Showing

1. Run `python context_menu_setup.py --check`
2. If not registered, run setup script as Administrator
3. Restart File Explorer: `taskkill /f /im explorer.exe && explorer.exe`

### Vault File Corrupted

- Keep `data/vault.bak` (automatic backup)
- Recover using recovery dialog on startup
- Ensure password is correct before operations

### Rate Limiting Triggered

- Wait 5 seconds and try again
- Verify caps lock is OFF
- Check password hasn't changed

---

## System Requirements

- **OS:** Windows 7 or later (Windows 10/11 recommended)
- **Python:** 3.9+ (for source installation)
- **RAM:** 512 MB minimum
- **Disk:** 100 MB for installation + vault size
- **GUI:** CustomTkinter (included in requirements)

---

## Dependencies

```
cryptography>=41.0.0       # AES-128-CBC encryption (Fernet)
customtkinter>=5.2.2       # Modern Windows GUI framework
```

See `requirements.txt` for complete list.

---

## License

VaultX - Secure File Encryption System
Created for Forensic Cyber Tech

---

## Support & Documentation

- **Issue Tracker:** Report bugs via GitHub Issues
- **Security Issues:** Contact directly (do not publish publicly)
- **Documentation:** See SECURITY_FIXES.md for vulnerability details

---

**Last Updated:** 2026-06-29
**Version:** 2.1.0 (Security Patches Applied)
