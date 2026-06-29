# VaultX Architecture & Implementation Guide

## Current Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         VaultX APPLICATION FLOW                             │
└─────────────────────────────────────────────────────────────────────────────┘

                                   START
                                    ↓
                    ┌───────────────────────────────┐
                    │   Check Configuration State   │
                    │  (config.json, vault.dat)     │
                    └───────────────────────────────┘
                                    ↓
                ┌───────────────────┼───────────────────┐
                │                   │                   │
    ┌───────────▼────────┐ ┌────────▼──────────┐ ┌──────▼────────────┐
    │  NO CONFIG FOUND   │ │ CONFIG EXISTS,    │ │ VAULT UNLOCKED    │
    │                    │ │ NO VAULT FILE     │ │ (Vault/ exists)   │
    │  Show: Welcome     │ │                   │ │                   │
    │  Action: Create    │ │ Show: Setup Info  │ │ Show: Terminal    │
    │  password          │ │ Action: Create    │ │ Action: Manage    │
    │                    │ │ vault folder      │ │ files             │
    └────────┬───────────┘ └────────┬──────────┘ └──────┬────────────┘
             │                      │                    │
             │                      │                    │
             └──────────┬───────────┴────────────────────┘
                        │
                        ▼
              ┌──────────────────────┐
              │   LOCK/UNLOCK LOGIC  │
              └──────────────────────┘
```

---

## Module Dependency Graph

```
main.py
  ↓
ui.py (CustomTkinter GUI)
  ├─→ config.py (password verification)
  ├─→ vault.py (lock/unlock operations)
  ├─→ file_import.py (import handler)
  └─→ exceptions.py (error definitions)

vault.py
  ├─→ config.py (verify_password, get_salt)
  ├─→ crypto.py (encrypt_bytes, decrypt_bytes)
  ├─→ archive.py (folder_to_bytes, bytes_to_folder)
  └─→ exceptions.py (InvalidPassword, CorruptedVault, etc.)

crypto.py
  └─→ cryptography.fernet (Fernet encryption)

archive.py
  └─→ zipfile (ZIP compression/extraction)

config.py
  └─→ hashlib, secrets (PBKDF2, constant-time comparison)

file_import.py
  ├─→ config.py (verify_password)
  └─→ shutil (file operations)

context_menu_setup.py
  └─→ winreg (Windows registry operations)
```

---

## Security Layer Stack

```
┌────────────────────────────────────────────────────┐
│          USER INTERACTION LAYER                    │
│  (UI, password dialogs, terminal commands)         │
├────────────────────────────────────────────────────┤
│          AUTHENTICATION LAYER                      │
│  • Password verification (config.py)               │
│  • Rate limiting (vault.py)                        │
│  • Constant-time comparison (secrets.compare_digest)
├────────────────────────────────────────────────────┤
│          ENCRYPTION LAYER                          │
│  • Fernet (AES-128-CBC + HMAC)                     │
│  • Key derivation (PBKDF2-HMAC-SHA256, 600k iter) │
│  • Authenticated encryption (built-in HMAC)       │
├────────────────────────────────────────────────────┤
│          ARCHIVE LAYER                             │
│  • ZIP compression (DEFLATE)                       │
│  • Path validation (ZIP slip prevention)           │
│  • Symlink rejection                               │
├────────────────────────────────────────────────────┤
│          FILE SYSTEM LAYER                         │
│  • Vault/ folder (plaintext, unlocked)             │
│  • vault.dat (encrypted, locked)                   │
│  • config.json (password hash)                     │
└────────────────────────────────────────────────────┘
```

---

## Data Flow: Lock Operation

```
User clicks "Lock"
  ↓
ui.py: _request_lock()
  ↓
vault.py: lock_vault(password)
  ├─→ config.py: verify_password() → Check stored hash (CONSTANT-TIME)
  │   ↓
  │   PBKDF2(password, salt, 600k) → Compare with stored_hash
  │   ├─→ Match: continue
  │   └─→ Mismatch: InvalidPassword exception
  │
  ├─→ archive.py: folder_to_bytes(Vault/)
  │   ├─→ Create in-memory BytesIO
  │   ├─→ ZIP all files in Vault/ (DEFLATE compression)
  │   └─→ Return compressed bytes
  │
  ├─→ crypto.py: encrypt_bytes(zip_bytes, password, salt)
  │   ├─→ generate_key(password, salt)
  │   │   ├─→ PBKDF2(password, salt, 600k) → 32-byte key
  │   │   └─→ base64_encode() → Fernet-compatible key
  │   │
  │   ├─→ Fernet.encrypt(zip_bytes)
  │   │   ├─→ Generate random IV (AES initialization vector)
  │   │   ├─→ AES-128-CBC encrypt
  │   │   └─→ HMAC-SHA256 authentication tag
  │   │
  │   └─→ Return encrypted bytes (IV + ciphertext + HMAC)
  │
  ├─→ Write to vault.tmp (atomic safety)
  │
  ├─→ Verify encryption: decrypt_bytes() on vault.tmp
  │   └─→ Validate HMAC + decrypt + verify ZIP integrity
  │
  ├─→ Atomic move: vault.tmp → vault.dat
  │
  ├─→ Delete Vault/ folder (no plaintext remains)
  │
  └─→ Success: "Vault locked."

File System Change:
  Before: Vault/ (plaintext files) + config.json (password hash)
  After:  vault.dat (encrypted) + config.json (password hash)
```

---

## Data Flow: Unlock Operation

```
User enters password
  ↓
ui.py: _submit_login()
  ↓
vault.py: unlock_vault(password)
  ├─→ _check_rate_limit("unlock")
  │   └─→ If 5+ failed attempts in 5s: REJECT + show countdown
  │
  ├─→ config.py: verify_password(password) ← SECURITY CHECKPOINT #1
  │   ├─→ Load config.json (contains stored_hash, salt)
  │   ├─→ PBKDF2(input_password, salt, 600k) → derived_hash
  │   ├─→ secrets.compare_digest(derived_hash, stored_hash)
  │   │   └─→ Constant-time comparison (prevents timing attacks)
  │   ├─→ Match: continue
  │   └─→ Mismatch: InvalidPassword exception
  │
  ├─→ Read vault.dat from disk
  │
  ├─→ crypto.py: decrypt_bytes(vault.dat, password, salt)
  │   ├─→ generate_key(password, salt) → Fernet key
  │   ├─→ Fernet.decrypt(vault.dat)
  │   │   ├─→ Verify HMAC-SHA256 (tampering detection)
  │   │   ├─→ AES-128-CBC decrypt using IV from ciphertext
  │   │   └─→ Return plaintext bytes
  │   │
  │   └─→ If HMAC fails: InvalidToken exception (wrong password or corrupted)
  │
  ├─→ archive.py: is_valid_zip_bytes(decrypted)
  │   └─→ Validate ZIP integrity with testzip()
  │
  ├─→ Create Vault/ folder
  │
  ├─→ archive.py: bytes_to_folder(zip_bytes, Vault/)
  │   ├─→ For each member in ZIP:
  │   │   ├─→ Resolve final path: Vault/ + member_name
  │   │   ├─→ Check path stays within Vault/ (prevent ZIP slip)
  │   │   ├─→ Reject if starts with ../ or ~
  │   │   └─→ Extract member
  │   │
  │   └─→ If path traversal detected: ValueError exception
  │
  ├─→ _reset_rate_limit("unlock")
  │   └─→ Clear failed attempt counter
  │
  └─→ Success: "Vault unlocked."

File System Change:
  Before: vault.dat (encrypted) + config.json
  After:  vault.dat (encrypted) + config.json + Vault/ (plaintext)
```

---

## Data Flow: File Import

```
User selects: "import"
  ↓
ui.py: _request_file_import()
  ├─→ Dialog: "Enter file/folder path"
  │   └─→ User enters: "C:\Documents\Secret.txt"
  │
  ├─→ file_import.py: validate_file_safety(path) ← SECURITY CHECKPOINT #1
  │   ├─→ Check file exists
  │   ├─→ Check not symlink
  │   ├─→ Check size <= 5GB
  │   ├─→ Check not executable (.exe, .dll, .sys, .bat, .cmd, .ps1)
  │   └─→ Return (is_safe, reason)
  │
  ├─→ If validation fails: Show error, cancel import
  │
  └─→ file_import.py: import_files([path], password) ← SECURITY CHECKPOINT #2
      ├─→ config.py: verify_password(password)
      │   └─→ PBKDF2 + constant-time comparison (same as unlock)
      │
      ├─→ Check Vault/ exists (must be unlocked)
      │
      ├─→ If file: shutil.copy2(source, Vault/) with rename if needed
      ├─→ If folder: shutil.copytree(source, Vault/)
      │
      └─→ Success: "Files imported successfully."

Result: Files now in plaintext Vault/ folder
Note: Must "lock" vault to encrypt imported files
```

---

## Authentication Flow Comparison

### Before Security Fixes ❌
```
unlock_vault(password)
  ├─→ Read encrypted vault.dat
  ├─→ Try Fernet.decrypt(vault.dat, password)
  │   └─→ If decryption succeeds: password is correct
  │   └─→ If InvalidToken: password might be wrong
  │
  └─→ No rate limiting: brute force possible
```

### After Security Fixes ✅
```
unlock_vault(password)
  ├─→ _check_rate_limit() ← RATE LIMITING
  │   └─→ Block if 5+ attempts in 5 seconds
  │
  ├─→ verify_password(password) ← PROPER AUTHENTICATION
  │   ├─→ Load stored_hash from config.json
  │   ├─→ PBKDF2(input_password, salt, 600k)
  │   ├─→ secrets.compare_digest() ← CONSTANT-TIME COMPARISON
  │   │   └─→ Prevents timing attacks
  │   ├─→ If hash matches: continue to decryption
  │   └─→ If hash mismatch: InvalidPassword exception
  │
  ├─→ Decrypt (only if password verified)
  │
  └─→ _reset_rate_limit() on success
```

---

## Encryption Key Derivation

```
Master Password Input
  ↓
PBKDF2-HMAC-SHA256
├─→ Input: password (UTF-8 bytes)
├─→ Salt: 128-bit cryptographic random (from config.json)
├─→ Hash Function: SHA256
├─→ Iterations: 600,000 (NIST SP 800-132 recommended)
├─→ Output Length: 32 bytes (256 bits)
│
↓
Two Outputs:
│
├─→ For Storage (config.py: save_new_password)
│   ├─→ hex_encode(32-byte key)
│   └─→ Store in config.json as "password_hash"
│
└─→ For Encryption (crypto.py: generate_key)
    ├─→ base64_urlsafe_encode(32-byte key)
    └─→ Pass to Fernet cipher
```

**Why 600,000 iterations?**
```
NIST SP 800-132 Recommendations (as of 2023):
- 2013: 64,000 minimum
- 2017: 100,000 minimum
- 2023: 600,000+ recommended (2024 and beyond)

Time per attempt: ~50-100ms on modern CPU
- Brute force 1M passwords: 14+ hours
- With rate limiting (5s lockout): 58+ days
```

---

## File Structure & Purpose

```
C:\FCT\VaultX/
│
├── main.py
│   └─ Entry point, calls ui.run()
│
├── ui.py (1,400+ lines)
│   ├─ VaultXApp (main Tkinter window)
│   ├─ PromptDialog (password input dialogs)
│   ├─ ProgressOverlay (progress indication)
│   └─ All user interaction logic
│
├── vault.py (290+ lines)
│   ├─ lock_vault(password) - Archive + encrypt
│   ├─ unlock_vault(password) - Decrypt + extract
│   ├─ Rate limiting module
│   └─ Vault state management
│
├── crypto.py (38 lines)
│   ├─ generate_key(password, salt)
│   ├─ encrypt_bytes(data, password, salt)
│   └─ decrypt_bytes(data, password, salt)
│
├── config.py (72 lines)
│   ├─ derive_key(password, salt) - Hash generation
│   ├─ verify_password(password) - Authentication ★ NEW
│   ├─ save_new_password(password)
│   └─ get_salt()
│
├── archive.py (52 lines)
│   ├─ folder_to_bytes(folder) - ZIP compression
│   ├─ bytes_to_folder(bytes, folder) - ZIP extraction + validation ★ FIXED
│   └─ is_valid_zip_bytes(bytes) - ZIP verification
│
├── file_import.py (97 lines) ★ NEW
│   ├─ import_files(file_paths, password)
│   └─ validate_file_safety(file_path)
│
├── context_menu_setup.py (132 lines) ★ NEW
│   ├─ register_context_menu(exe_path)
│   ├─ unregister_context_menu()
│   └─ is_registered()
│
├── constants.py
│   └─ Configuration constants
│
├── exceptions.py
│   └─ Custom exception classes
│
├── build_exe.bat ★ NEW
│   └─ PyInstaller automation script
│
├── README.md ★ NEW
│   └─ Complete documentation
│
├── SECURITY_FIXES.md
│   └─ Security vulnerability documentation
│
├── ARCHITECTURE.md (this file) ★ NEW
│   └─ System design and implementation details
│
├── data/
│   ├─ config.json (password hash + salt)
│   ├─ vault.dat (encrypted vault)
│   ├─ vault.tmp (temporary during operations)
│   └─ vault.bak (backup during operations)
│
├── Vault/
│   └─ [User files - plaintext when unlocked]
│
└── logs/
    └─ vault.log (application log)
```

---

## Cryptographic Algorithms Used

| Component | Algorithm | Details | Why Chosen |
|-----------|-----------|---------|-----------|
| **Key Derivation** | PBKDF2-HMAC-SHA256 | 600,000 iterations, 128-bit salt | NIST standard, GPU-resistant |
| **Encryption** | AES-128-CBC | 128-bit key, random IV | Industry standard, NIST approved |
| **Authentication** | HMAC-SHA256 | Fernet built-in | Detects tampering, prevents forgery |
| **Hashing** | SHA256 | For password storage | One-way, fast verification |
| **Comparison** | Constant-time | `secrets.compare_digest()` | Prevents timing attacks |
| **Compression** | DEFLATE | Standard ZIP algorithm | Good compression, no crypto needed |
| **Random** | Python `secrets` module | OS CSPRNG | Cryptographically secure |

---

## Future Enhancement Ideas

### Phase 3: Advanced Features
- [ ] Multi-user support with separate passwords
- [ ] Partial unlock (select specific files)
- [ ] Automatic cloud backup integration
- [ ] File versioning/history
- [ ] Secure file deletion (prevents recovery)

### Phase 4: Performance
- [ ] Streaming encryption for large files
- [ ] Parallel compression/encryption
- [ ] Progress indicator for large vaults

### Phase 5: Integration
- [ ] Mobile app for remote access
- [ ] Web interface for management
- [ ] Audit log with timestamps
- [ ] Email notifications on vault access

---

## Quick Reference: Key Functions

### Authentication
- `verify_password(password)` - Check password
- `derive_key(password, salt)` - Generate hash

### Encryption
- `encrypt_bytes(data, password, salt)` - Encrypt
- `decrypt_bytes(data, password, salt)` - Decrypt

### Archive
- `folder_to_bytes(folder)` - Compress
- `bytes_to_folder(bytes, folder)` - Extract (with validation)

### File Import
- `import_files(file_paths, password)` - Import with auth
- `validate_file_safety(file_path)` - Pre-import check

### Rate Limiting
- `_check_rate_limit()` - Enforce limits
- `_reset_rate_limit()` - Clear on success

### Vault Operations
- `lock_vault(password)` - Encrypt & compress
- `unlock_vault(password)` - Decrypt & extract

---

**Architecture Version:** 2.1.0
**Last Updated:** 2026-06-29
**Status:** Production Ready (with security fixes)
