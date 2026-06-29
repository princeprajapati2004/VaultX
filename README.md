# VaultX — Secure Per-File Encrypted Vault

A secure offline desktop application that encrypts personal files individually using
**Argon2id** key derivation and **XChaCha20-Poly1305** authenticated encryption.

**Version:** 3.0.0 | **Platform:** Windows | **Mode:** Personal offline use

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture & Workflow](#architecture--workflow)
3. [Security Features](#security-features)
4. [File Format](#vx-file-format)
5. [Command Reference](#command-reference)
6. [Migration from v2](#migration-from-v2)
7. [Building .EXE](#building-exe)
8. [Context Menu Integration](#context-menu-integration)
9. [Configuration Reference](#configuration-reference)
10. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Installation

```bash
# Install dependencies (includes Argon2 + libsodium bindings)
pip install -r requirements.txt

# Run VaultX
python main.py
```

### First Launch

1. **Create Vault** — Set a strong master password (minimum 8 characters)
2. **Add Files** — Place files in the `Vault/` folder or use the `import` command
3. **Lock Vault** — Encrypts every file individually and removes `Vault/`
4. **Unlock** — Enter password to restore `Vault/` with all decrypted files

---

## Architecture & Workflow

### Application States

| State | Condition | Screen |
|-------|-----------|--------|
| **NO_CONFIG** | `VaultData/config.json` missing | Welcome → Create password |
| **LOCKED** | Config exists, `Vault/` absent | Login screen |
| **UNLOCKED** | Config exists, `Vault/` present | Terminal |
| **LEGACY** | `data/config.json` from v2 found | Migration notice |

### Directory Structure

```
C:\FCT\VaultX/
├── main.py                  Entry point + crypto self-test gate
├── ui.py                    CustomTkinter GUI
├── vault.py                 lock_vault / unlock_vault / recovery
├── crypto.py                Argon2id KDF + XChaCha20-Poly1305 primitives
├── config.py                Password management (save / verify / get_master_key)
├── metadata.py              Encrypted metadata index
├── streaming.py             64 KB chunk streaming encryption
├── file_import.py           Validated import pipeline
├── archive.py               Legacy ZIP helpers (kept for reference)
├── context_menu_setup.py    Windows registry context menu
├── constants.py             All shared paths and constants
├── exceptions.py            Exception hierarchy
├── requirements.txt
├── build_exe.bat
│
├── VaultData/               Created on first setup
│   ├── encrypted/           .vx files — one per stored file
│   ├── metadata/            reserved for per-file metadata shards
│   ├── temp/                staging during atomic lock operations
│   ├── backup/              snapshot before each lock commit
│   ├── logs/vault.log
│   ├── config.json          Argon2id parameters + key_hash + salt
│   └── metadata.json.vx     encrypted metadata index
│
├── Vault/                   Plaintext working directory (unlocked only)
│
└── data/                    Legacy v2 directory (presence triggers migration notice)
```

---

## Security Features

### Key Derivation — Argon2id

```
Password → Argon2id → 32-byte Master Key
  ├─ memory:      64 MiB  (GPU attacks require expensive RAM per attempt)
  ├─ time_cost:   3 iterations
  ├─ parallelism: 4 threads
  └─ salt:        32 cryptographically random bytes (stored in config.json)
```

A SHA-256 hash of the master key is stored as `key_hash` for password verification.
The master key itself is never stored on disk.

### Encryption — XChaCha20-Poly1305 AEAD

- **256-bit key**, **192-bit (24-byte) random nonce per chunk**
- **16-byte Poly1305 authentication tag** per chunk — any single bit-flip is detected
- **AAD** = `file_id_bytes || chunk_index` — prevents cross-file or within-file chunk reordering
- Provided by **libsodium** via PyNaCl — same library trusted by Signal, WhatsApp, WireGuard

### Per-File Isolation

Every file becomes its own independent `.vx` object:

- Compromise of one file's nonce does not affect other files
- Corruption in one file does not corrupt others
- Missing or replaced files are detected via the encrypted metadata index

### Integrity Verification

On every unlock:

1. **Metadata AEAD tag** verified first (tampered metadata → abort)
2. **Per-chunk Poly1305 tag** verified as each chunk is decrypted
3. **SHA-256 checksum** of reconstructed plaintext verified against metadata record

### Startup Self-Test

`crypto.run_self_test()` runs before the UI opens and verifies:
- Argon2id produces correct key length
- XChaCha20-Poly1305 roundtrip is correct
- Tampered ciphertext is rejected
- Wrong key is rejected
- Wrong AAD is rejected

If any check fails VaultX shows an error and exits.

### Rate Limiting

- 5 failed unlock attempts → 30-second lockout
- Counter resets on successful unlock
- Constant-time password comparison (`secrets.compare_digest`)

### File Import Policy

| Check | Limit |
|-------|-------|
| Maximum file size | 150 MB |
| Blocked types | `.exe .dll .sys .bat .cmd .ps1 .msi .scr .vbs …` |
| Symbolic links | Rejected |

---

## .vx File Format

Every encrypted file stored in `VaultData/encrypted/` uses this binary layout:

```
HEADER  8 bytes:
  magic[4]    = b"VXFL"
  version[1]  = 1
  flags[1]    = bit-0: payload was zlib-compressed before encryption
  reserved[2] = 0x00 0x00

CHUNKS  (repeated for every 64 KB block):
  nonce[24]          fresh random XChaCha20 nonce
  ciphertext_len[4]  LE uint32 — length of following data (includes 16-byte tag)
  ciphertext[N]      XChaCha20-Poly1305 encrypted payload + Poly1305 tag
```

Compression is applied only to formats that benefit (`.txt`, `.json`, `.csv`, Python
source, etc.).  Already-compressed formats (`.jpg`, `.png`, `.mp4`, `.zip`, …) are
stored without an extra compression pass.

---

## Command Reference

### Terminal Commands (vault unlocked)

| Command | Description |
|---------|-------------|
| `open` | Open `Vault/` in Windows Explorer |
| `lock` | Encrypt all files in `Vault/` and remove the folder |
| `import` | Add a file or folder to `Vault/` (validated pipeline) |
| `passwd` | Change the master password and re-encrypt |
| `status` | Show current vault state |
| `help` | List all commands |
| `clear` | Clear terminal output |
| `exit` | Close VaultX |

### Password Change Flow

```
passwd
  → Dialog: enter new password (min 8 chars, confirmed)
  → save_new_password(new_pwd)    — new Argon2id config written
  → lock_vault(new_pwd)           — all Vault/ files re-encrypted with new key
  → unlock_vault(new_pwd)         — verify new key works; restore Vault/
  → "Password updated."
```

### Recovery Dialog

If VaultX is interrupted during a lock operation, temp `.vx` files may remain in
`VaultData/temp/`.  On next startup, a recovery dialog offers:

- **Recover** — promotes temp files to `encrypted/`
- **Delete** — removes temp files and starts fresh

---

## Migration from v2

VaultX v3 uses a completely different cryptographic architecture and is not backward
compatible with v2 vaults.

**How to migrate:**

1. Open your vault with **VaultX v2.x**
2. Unlock and copy all files out of `Vault/` to a temporary location
3. Close v2
4. Run **VaultX v3** → create a new vault → import the files
5. Delete the temporary copies when you are satisfied

VaultX v3 detects the presence of a `data/config.json` from v2 and shows a migration
notice instead of attempting to use the old format.

---

## Building .EXE

```batch
# From the project root (VaultX.venv activated):
pip install pyinstaller

pyinstaller --onefile --windowed --name VaultX ^
  --add-data "VaultData;VaultData" ^
  main.py

# Output: dist\VaultX.exe
```

Distribute only `VaultX.exe`.  No Python or library installation needed on end-user machines.

---

## Context Menu Integration

### Register (requires Administrator)

```bash
python context_menu_setup.py --register "C:\path\to\VaultX.exe"
```

### Check registration

```bash
python context_menu_setup.py --check
```

### Unregister

```bash
python context_menu_setup.py --unregister
```

Adds right-click → **"Add to VaultX"** for files and folders in Windows Explorer.

---

## Configuration Reference

**`VaultData/config.json`** (created on first setup):

```json
{
    "version": 3,
    "kdf": "argon2id",
    "argon2_time_cost": 3,
    "argon2_memory_cost": 65536,
    "argon2_parallelism": 4,
    "argon2_hash_len": 32,
    "salt": "<64-hex-chars>",
    "key_hash": "<64-hex-chars>"
}
```

| Field | Description |
|-------|-------------|
| `version` | Config schema version (3 = Argon2id/XChaCha20) |
| `kdf` | Key derivation function identifier |
| `argon2_*` | Argon2id parameters used for this vault |
| `salt` | 32-byte CSPRNG salt (hex) — unique per vault |
| `key_hash` | SHA-256(master_key) — used for password verification |

---

## Troubleshooting

### "Cryptographic self-test failed"

A library is missing or corrupted.  Reinstall dependencies:

```bash
pip install -r requirements.txt
```

### "Wrong password or corrupted vault"

- Passwords are case-sensitive — check CAPS LOCK
- If the config was corrupted, no recovery is possible (by design)

### "Legacy vault format detected"

Your vault was created with VaultX v2.  See [Migration from v2](#migration-from-v2).

### Rate limit triggered

Wait 30 seconds, then retry.  Verify the correct password.

### Context menu not appearing

Re-run `context_menu_setup.py --register` as Administrator, then restart Explorer:

```
taskkill /f /im explorer.exe && explorer.exe
```

### Recovery dialog on startup

An interrupted lock operation was detected.  Choose **Recover** to complete it or
**Delete** to clean up and start from the current state of `Vault/`.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `argon2-cffi` | Argon2id key derivation |
| `pynacl` | XChaCha20-Poly1305 AEAD (libsodium bindings) |
| `cryptography` | Retained for any legacy helper paths |
| `customtkinter` | Modern Windows GUI framework |
| `psutil` | System utilities |
| `watchdog` | File system monitoring |

---

## System Requirements

- **OS:** Windows 10 / 11 (64-bit)
- **Python:** 3.9+ (source installation)
- **RAM:** 256 MB minimum; 64 MB reserved per Argon2id derivation
- **Disk:** Installation + vault file sizes

---

**Last Updated:** 2026-06-29  
**Version:** 3.0.0  
**For:** Forensic Cyber Tech — Personal offline use
