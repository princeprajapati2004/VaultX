# VaultX Architecture & Implementation Guide — v3.0

## Application Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         VaultX APPLICATION FLOW (v3)                        │
└─────────────────────────────────────────────────────────────────────────────┘

                                   START
                                    ↓
                     ┌──────────────────────────────┐
                     │   Crypto self-test            │
                     │   Argon2id + XChaCha20-Poly  │
                     │   Abort if any check fails   │
                     └──────────────────────────────┘
                                    ↓
                    ┌───────────────────────────────┐
                    │   Check Configuration State   │
                    │  (VaultData/config.json)      │
                    └───────────────────────────────┘
                                    ↓
         ┌──────────────────────────┼───────────────────────┐
         │                          │                       │
┌────────▼──────────┐  ┌────────────▼───────────┐  ┌───────▼────────────┐
│  LEGACY DETECTED  │  │  NO CONFIG FOUND       │  │  CONFIG EXISTS     │
│  (data/config.json│  │                        │  │                    │
│  from v2 found)   │  │  Show: Welcome         │  │  if Vault/ exists: │
│                   │  │  Action: Create        │  │    Show: Terminal  │
│  Show: Migration  │  │  password + vault      │  │  else:             │
│  notice           │  │                        │  │    Show: Login     │
└───────────────────┘  └────────────────────────┘  └────────────────────┘
```

---

## Module Dependency Graph

```
main.py  ──→  crypto.run_self_test()  (startup abort-gate)
  ↓
ui.py (CustomTkinter GUI)
  ├─→ config.py  (save_new_password, verify_password, get_master_key, is_legacy_vault)
  ├─→ vault.py   (lock_vault, unlock_vault, recovery functions)
  ├─→ file_import.py  (import_files, validate_file_safety)
  ├─→ constants.py
  └─→ exceptions.py

vault.py
  ├─→ config.py    (verify_password, get_master_key)
  ├─→ metadata.py  (load_metadata, save_metadata, build_file_record)
  ├─→ streaming.py (encrypt_file, decrypt_file, should_compress)
  └─→ exceptions.py

config.py
  └─→ crypto.py    (derive_master_key, generate_salt, compute_sha256)

crypto.py
  ├─→ argon2.low_level  (Argon2id key derivation)
  └─→ nacl.bindings     (XChaCha20-Poly1305 AEAD)

metadata.py
  └─→ crypto.py    (encrypt_chunk, decrypt_chunk, generate_nonce)

streaming.py
  └─→ crypto.py    (encrypt_chunk, decrypt_chunk, generate_nonce)

file_import.py
  └─→ config.py    (verify_password)

context_menu_setup.py
  └─→ winreg       (Windows registry operations)
```

---

## Security Layer Stack

```
┌────────────────────────────────────────────────────┐
│          USER INTERACTION LAYER                    │
│  (UI, password dialogs, terminal commands)         │
├────────────────────────────────────────────────────┤
│          AUTHENTICATION LAYER                      │
│  • Argon2id key derivation (config.py)             │
│  • SHA-256 key-hash comparison (secrets.compare_   │
│    digest — constant-time, timing-attack-safe)     │
│  • Rate limiting: 5 attempts → 30 s lockout        │
├────────────────────────────────────────────────────┤
│          ENCRYPTION LAYER                          │
│  • XChaCha20-Poly1305 AEAD (per file, per chunk)   │
│  • 24-byte random nonce per chunk                  │
│  • 16-byte Poly1305 authentication tag per chunk   │
│  • AAD = file_id + chunk_index (anti-reorder)      │
├────────────────────────────────────────────────────┤
│          KEY DERIVATION LAYER                      │
│  • Argon2id (m=65536 KiB, t=3, p=4)                │
│  • 32-byte random Argon2 salt                      │
│  • 32-byte master key output                       │
├────────────────────────────────────────────────────┤
│          STORAGE LAYER                             │
│  • Per-file .vx objects (VaultData/encrypted/)     │
│  • Encrypted metadata index (metadata.json.vx)     │
│  • SHA-256 checksum per file in metadata           │
│  • Atomic writes — temp/ before commit             │
└────────────────────────────────────────────────────┘
```

---

## .vx Encrypted File Format

```
HEADER  8 bytes:
  magic[4]    = b"VXFL"
  version[1]  = 1
  flags[1]    = bit-0: payload zlib-compressed before encryption
  reserved[2] = 0x00 0x00

CHUNKS  (repeated for every 64 KB block of the original file):
  nonce[24]          — fresh random XChaCha20 nonce
  ciphertext_len[4]  — LE uint32 (includes 16-byte Poly1305 tag)
  ciphertext[N]      — XChaCha20-Poly1305 ciphertext + tag

AAD per chunk = file_id_utf8 || chunk_index_LE_uint32
```

---

## Data Flow: Lock Operation

```
User clicks "Lock"
  ↓
ui.py: _request_lock()
  ↓
vault.py: lock_vault(password)
  ├─→ config.py: get_master_key(password)
  │     └─→ Argon2id(password, stored_salt) → 32-byte master_key
  │
  ├─→ For each file in Vault/:
  │   ├─→ validate size ≤ 150 MB → FileTooLarge if exceeded
  │   ├─→ generate UUID file_id
  │   ├─→ streaming.py: encrypt_file(src, TEMP_DIR/uuid.vx, master_key, file_id)
  │   │   ├─→ Decide zlib compression (extension-based policy)
  │   │   ├─→ Read 64 KB chunks in a loop:
  │   │   │   ├─→ hash_plaintext_chunk (SHA-256 accumulator)
  │   │   │   ├─→ zlib.compress(chunk) if compressible
  │   │   │   ├─→ nonce = generate_nonce() [24 random bytes]
  │   │   │   ├─→ aad = file_id + chunk_index
  │   │   │   └─→ XChaCha20-Poly1305 encrypt → write [nonce|len|ciphertext]
  │   │   └─→ Return (sha256_hex, compressed)
  │   └─→ metadata.build_file_record() → FileRecord
  │
  ├─→ Backup existing .vx files to VaultData/backup/
  ├─→ Commit all temp .vx → VaultData/encrypted/
  ├─→ metadata.save_metadata(meta, master_key)  [encrypted with XChaCha20]
  ├─→ Remove backup files
  └─→ shutil.rmtree(Vault/)

On failure: temp files deleted, backup restored atomically.
```

---

## Data Flow: Unlock Operation

```
User enters password
  ↓
ui.py: _submit_login()
  ↓
vault.py: unlock_vault(password)
  ├─→ _check_rate_limit()  — 5 failures → 30 s lockout
  ├─→ config.py: verify_password(password) ← SECURITY CHECKPOINT
  │     ├─→ Argon2id(password, stored_salt) → master_key
  │     ├─→ SHA-256(master_key) → derived_hash
  │     └─→ secrets.compare_digest(derived_hash, stored_key_hash)
  │
  ├─→ config.py: get_master_key(password) → master_key (re-derived)
  │
  ├─→ metadata.load_metadata(master_key)
  │     ├─→ XChaCha20-Poly1305 decrypt metadata.json.vx
  │     └─→ Parse JSON → VaultMetadata
  │
  ├─→ mkdir Vault/
  │
  ├─→ For each FileRecord in metadata:
  │   ├─→ Check .vx file exists → VaultNotFound if missing
  │   ├─→ streaming.py: decrypt_file(vx_path, Vault/name, master_key, file_id, sha256)
  │   │   ├─→ Read and verify .vx header magic + version
  │   │   ├─→ For each chunk:
  │   │   │   ├─→ Read nonce (24 bytes)
  │   │   │   ├─→ Read ciphertext_len + ciphertext
  │   │   │   ├─→ XChaCha20-Poly1305 decrypt (verify Poly1305 tag)
  │   │   │   └─→ zlib.decompress if compressed flag set
  │   │   └─→ Verify SHA-256 of reconstructed plaintext vs metadata
  │   └─→ Write plaintext file to Vault/
  │
  ├─→ _reset_rate_limit()
  └─→ "Vault unlocked."

On any failure: Vault/ removed entirely.
```

---

## Data Flow: File Import

```
User selects: "import"
  ↓
ui.py: _request_file_import()
  ├─→ file_import.py: validate_file_safety(path)
  │   ├─→ Check exists
  │   ├─→ Reject symlinks
  │   ├─→ Check size ≤ 150 MB
  │   └─→ Reject executable extensions (.exe, .dll, .sys, .bat, …)
  │
  └─→ file_import.py: import_files([path], session_password)
      ├─→ verify_password(password)  — constant-time Argon2id comparison
      ├─→ Check Vault/ exists (vault must be unlocked)
      └─→ shutil.copy2 / copytree → Vault/ (with conflict rename)

Files in Vault/ are encrypted on the next lock_vault() call.
```

---

## Key Derivation: Argon2id

```
Master Password
  ↓
Argon2id (argon2-cffi library → libargon2)
  ├─→ time_cost:    3 iterations
  ├─→ memory_cost:  65,536 KiB  (64 MiB)
  ├─→ parallelism:  4 threads
  ├─→ hash_len:     32 bytes
  └─→ salt:         32 cryptographically random bytes (stored in config.json)
  ↓
32-byte Master Key

For password verification:
  SHA-256(master_key) → stored as "key_hash" in config.json
  Compare with secrets.compare_digest() [constant-time]
```

**Why Argon2id?**
- Memory-hard: GPU/ASIC brute-force attacks require expensive RAM per attempt
- Time-hard: configurable iteration count
- Parallelism-hard: scales to multiple cores for legitimate use
- OWASP 2023 recommended KDF for passwords

---

## File Structure

```
C:\FCT\VaultX/
│
├── main.py              Entry point with crypto self-test gate
├── ui.py                CustomTkinter GUI (all screens + terminal)
├── vault.py             lock_vault / unlock_vault / recovery
├── crypto.py            Argon2id KDF + XChaCha20-Poly1305 primitives
├── config.py            Password management, save/verify/get_master_key
├── metadata.py          Encrypted metadata index (FileRecord, VaultMetadata)
├── streaming.py         64 KB chunk streaming encryption/decryption
├── file_import.py       Validated file copy pipeline into Vault/
├── archive.py           Legacy ZIP helpers (kept for reference only)
├── context_menu_setup.py Windows registry context menu integration
├── constants.py         All shared constants and paths
├── exceptions.py        Full exception hierarchy
├── requirements.txt
├── build_exe.bat
│
├── VaultData/           Vault storage (created on first setup)
│   ├── encrypted/       .vx encrypted files (one per stored file)
│   ├── metadata/        reserved for per-file metadata shards
│   ├── temp/            staging area for atomic lock operations
│   ├── backup/          snapshot taken before each lock commit
│   ├── logs/            vault.log
│   ├── config.json      Argon2id params + key_hash + salt
│   └── metadata.json.vx encrypted metadata index
│
├── Vault/               Plaintext working directory (only when unlocked)
│   └── [user files]
│
└── data/                Legacy v2 directory (detected for migration notice)
    └── config.json      (if present: triggers legacy vault warning)
```

---

## Cryptographic Algorithm Summary

| Component | Algorithm | Parameters | Standard |
|-----------|-----------|------------|----------|
| **Key derivation** | Argon2id | m=64 MiB, t=3, p=4, len=32 B | RFC 9106, OWASP 2023 |
| **Encryption** | XChaCha20-Poly1305 | 256-bit key, 192-bit nonce | RFC 8439 / libsodium |
| **Authentication** | Poly1305 MAC | 128-bit tag per chunk | RFC 8439 |
| **Integrity** | SHA-256 checksum | per-file plaintext | FIPS 180-4 |
| **Nonce** | CSPRNG | 24 bytes per chunk | OS `secrets` module |
| **Salt** | CSPRNG | 32 bytes per vault | OS `secrets` module |
| **Comparison** | Constant-time | `secrets.compare_digest` | Timing-attack resistant |
| **Compression** | zlib / DEFLATE | level 6, selective | RFC 1951 |

---

## Startup Self-Test Coverage

On every launch `crypto.run_self_test()` verifies:

1. Argon2id produces a 32-byte key
2. `generate_nonce()` produces a 24-byte nonce
3. Encrypt → decrypt roundtrip returns original plaintext
4. Ciphertext length = plaintext + 16-byte tag
5. Tampered ciphertext is rejected (raises `AuthenticationFailed`)
6. Wrong key is rejected
7. Wrong AAD is rejected
8. SHA-256 is deterministic

---

**Architecture Version:** 3.0.0
**Last Updated:** 2026-06-29
