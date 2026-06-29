# VaultX Security — Vulnerability History & Phase 3 Hardening

## v3.0 — Phase 3 Cryptographic Architecture Upgrade

### Overview

v3.0 replaces the entire cryptographic stack with modern primitives and migrates from a
single encrypted archive to a per-file encrypted vault.  Every item below represents
a deliberate security improvement, not a bug fix.

---

### 1. ✅ Replaced PBKDF2 with Argon2id (KDF)

**Previous:** PBKDF2-HMAC-SHA256 at 600,000 iterations  
**Now:** Argon2id — memory-hard, time-hard, parallelism-hard

| Parameter | Value |
|-----------|-------|
| Memory    | 64 MiB (65,536 KiB) |
| Time cost | 3 iterations |
| Parallelism | 4 threads |
| Output    | 32-byte master key |
| Salt      | 32 bytes CSPRNG (per vault) |

**Why:** PBKDF2 is compute-bound only.  A modern GPU can test ~1 billion PBKDF2-SHA256
attempts/second.  Argon2id requires 64 MiB of RAM per attempt, reducing GPU parallelism
by ~1000× and making ASIC attacks economically infeasible.

---

### 2. ✅ Replaced AES-128-CBC + Fernet with XChaCha20-Poly1305

**Previous:** Fernet (AES-128-CBC + HMAC-SHA256)  
**Now:** XChaCha20-Poly1305 AEAD (via libsodium / PyNaCl)

| Property | Old | New |
|----------|-----|-----|
| Key size | 128-bit (AES-128) | 256-bit (XChaCha20) |
| Nonce | 128-bit, IV in ciphertext | 192-bit, fresh random per chunk |
| Authentication | HMAC-SHA256 (separate MAC-then-encrypt) | Poly1305 (integrated AEAD) |
| Nonce collision risk | Birthday problem at 2^64 | Birthday problem at 2^96 |

**Why:** Fernet is not AEAD — it uses Encrypt-then-MAC which is correct but brittle to
implement.  XChaCha20-Poly1305 is a single authenticated primitive with no risk of
MAC-encrypt ordering bugs.  The 192-bit nonce eliminates practical nonce-reuse concerns.

---

### 3. ✅ Replaced Single Archive with Per-File Encrypted Objects

**Previous:** All files → ZIP → single AES-CBC blob (`vault.dat`)  
**Now:** Each file independently encrypted as `<uuid>.vx`

**Why per-file encryption matters:**
- Decrypting one file does not expose plaintext of others
- Corruption in one `.vx` file does not destroy the whole vault
- Each file gets its own nonces; no cross-file nonce relationships
- Metadata is authenticated separately (can detect missing files)

---

### 4. ✅ Per-Chunk Authentication Tags

Every 64 KB chunk of every file carries its own 16-byte Poly1305 authentication tag.

**AAD = `file_id_bytes || chunk_index_LE_uint32`**

This prevents:
- Reordering chunks within a file
- Moving chunks between different files
- Replaying chunks from a previous vault version

Any modification to any byte of any chunk causes decryption to fail with
`CorruptedVault` before any plaintext is written.

---

### 5. ✅ Encrypted Metadata with Integrity Verification

The metadata index (`metadata.json.vx`) is itself encrypted with XChaCha20-Poly1305.

Every unlock operation verifies the metadata AEAD tag before touching any `.vx` file.
A tampered or missing metadata file raises `MetadataCorrupted` and aborts immediately.

---

### 6. ✅ Per-File SHA-256 Integrity Checksum

After decrypting each file the reconstructed plaintext is compared against the SHA-256
checksum stored (encrypted) in the metadata index.

A checksum mismatch raises `CorruptedVault` — the partially-written file is not presented
to the user.

---

### 7. ✅ Cryptographic Self-Test on Every Startup

`crypto.run_self_test()` is called by `main.py` before the UI initialises.

Tests covered:
1. Argon2id produces a 32-byte key
2. `generate_nonce()` produces a 24-byte value
3. Encrypt → decrypt roundtrip is correct
4. Ciphertext is exactly `len(plaintext) + 16` bytes
5. Tampered ciphertext is rejected
6. Wrong key is rejected
7. Wrong AAD is rejected
8. SHA-256 is deterministic

If any test fails VaultX shows an error dialog and exits.  A corrupted build or missing
library cannot silently produce wrong ciphertext.

---

### 8. ✅ Streaming Encryption — No Full-File RAM Spikes

Files are processed in 64 KB chunks throughout encryption and decryption.

Peak RAM usage ≈ one chunk buffer + overhead, regardless of file size.
The 150 MB import limit ensures individual operations remain bounded.

---

### 9. ✅ Selective Compression Policy

Previously the entire vault was ZIP-compressed regardless of content type.
Now:

- **Already-compressed formats** (JPEG, PNG, MP4, PDF, ZIP, …) — compression skipped
- **Text/source formats** (TXT, JSON, CSV, Python, …) — zlib level-6 applied

This prevents the CRIME/BREACH-class problem where compressing mixed content can
leak cross-file information through size correlations, and avoids inflating already-dense files.

---

### 10. ✅ Atomic Writes with Backup and Rollback

Lock operation phases:
1. Encrypt all files into `VaultData/temp/` (staging)
2. Move existing `.vx` files to `VaultData/backup/`
3. Commit staged files into `VaultData/encrypted/`
4. Write encrypted metadata
5. Remove backup, remove `Vault/`

If any step fails, the backup is restored and temp files are cleaned.
At no point can a failure leave the vault in a state with neither encrypted nor plaintext files.

---

## v2.1 — Critical Vulnerability Patches (Historical)

The five vulnerabilities fixed in v2.1.0 were:

| # | Issue | Fix |
|---|-------|-----|
| 1 | Password hash stored but never verified | Added `verify_password()` with constant-time comparison |
| 2 | No rate limiting on unlock attempts | 5 failures → 30 s lockout |
| 3 | ZIP slip vulnerability in extraction | Path validation per member before extract |
| 4 | Plaintext password left in UI widgets | `_clear_password_fields()` called after every use |
| 5 | Auth failures only detected at decrypt time | Explicit hash check before decryption |

All five remain present and effective in v3.0.

---

## Verification Checklist — v3.0

- ✅ Argon2id KDF with OWASP high-value-secret parameters
- ✅ XChaCha20-Poly1305 AEAD with per-chunk authentication
- ✅ Per-file isolation — each `.vx` is an independent encrypted object
- ✅ Metadata encrypted and authenticated separately
- ✅ SHA-256 plaintext checksum verified after each decrypt
- ✅ Cryptographic self-test aborts startup on failure
- ✅ Streaming I/O — no full-file RAM spikes
- ✅ 150 MB file size limit enforced before encryption begins
- ✅ Selective compression — no compression for pre-compressed formats
- ✅ Atomic lock with temp/backup/commit/rollback
- ✅ Rate limiting: 5 attempts → 30 s lockout
- ✅ Constant-time password comparison
- ✅ Legacy vault detection with migration notice
- ✅ Executable file types blocked at import

---

**Status:** All cryptographic primitives verified by automated self-test ✅  
**Version:** 3.0.0  
**Date:** 2026-06-29
