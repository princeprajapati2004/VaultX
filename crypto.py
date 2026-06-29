"""Modern cryptographic primitives for VaultX — Argon2id + XChaCha20-Poly1305."""

from __future__ import annotations

import hashlib
import secrets

from argon2.low_level import Type, hash_secret_raw
from nacl.bindings import (
    crypto_aead_xchacha20poly1305_ietf_ABYTES,
    crypto_aead_xchacha20poly1305_ietf_KEYBYTES,
    crypto_aead_xchacha20poly1305_ietf_NPUBBYTES,
    crypto_aead_xchacha20poly1305_ietf_decrypt,
    crypto_aead_xchacha20poly1305_ietf_encrypt,
)

from constants import (
    ARGON2_HASH_LEN,
    ARGON2_MEMORY_COST,
    ARGON2_PARALLELISM,
    ARGON2_SALT_LEN,
    ARGON2_TIME_COST,
)
from exceptions import AuthenticationFailed, CryptoSelfTestFailed

# Sizes exposed for other modules
NONCE_SIZE: int = crypto_aead_xchacha20poly1305_ietf_NPUBBYTES   # 24 bytes
KEY_SIZE: int = crypto_aead_xchacha20poly1305_ietf_KEYBYTES       # 32 bytes
TAG_SIZE: int = crypto_aead_xchacha20poly1305_ietf_ABYTES         # 16 bytes


def generate_salt() -> bytes:
    """Generate a cryptographically random 32-byte Argon2id salt."""
    return secrets.token_bytes(ARGON2_SALT_LEN)


def generate_nonce() -> bytes:
    """Generate a cryptographically random 24-byte XChaCha20-Poly1305 nonce."""
    return secrets.token_bytes(NONCE_SIZE)


def derive_master_key(
    password: str,
    salt: bytes,
    *,
    time_cost: int = ARGON2_TIME_COST,
    memory_cost: int = ARGON2_MEMORY_COST,
    parallelism: int = ARGON2_PARALLELISM,
) -> bytes:
    """
    Derive a 32-byte master key from a password using Argon2id.

    Parameters match OWASP high-value-secret profile:
    m=65536 KiB, t=3, p=4.
    """
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=time_cost,
        memory_cost=memory_cost,
        parallelism=parallelism,
        hash_len=ARGON2_HASH_LEN,
        type=Type.ID,
    )


def encrypt_chunk(chunk: bytes, key: bytes, nonce: bytes, aad: bytes = b"") -> bytes:
    """
    Encrypt a data chunk with XChaCha20-Poly1305 AEAD.

    Returns ciphertext with the 16-byte Poly1305 authentication tag appended.
    The AAD is authenticated but not encrypted.
    """
    return crypto_aead_xchacha20poly1305_ietf_encrypt(
        message=chunk,
        aad=aad,
        nonce=nonce,
        key=key,
    )


def decrypt_chunk(ciphertext: bytes, key: bytes, nonce: bytes, aad: bytes = b"") -> bytes:
    """
    Decrypt and authenticate a XChaCha20-Poly1305 chunk.

    Raises AuthenticationFailed if the authentication tag is invalid,
    indicating tampering, corruption, or a wrong key.
    """
    try:
        return crypto_aead_xchacha20poly1305_ietf_decrypt(
            ciphertext=ciphertext,
            aad=aad,
            nonce=nonce,
            key=key,
        )
    except Exception as exc:
        raise AuthenticationFailed(
            "XChaCha20-Poly1305 authentication tag verification failed."
        ) from exc


def compute_sha256(data: bytes) -> str:
    """Return the hex-encoded SHA-256 digest of the given bytes."""
    return hashlib.sha256(data).hexdigest()


def run_self_test() -> None:
    """
    Verify all cryptographic primitives at application startup.

    Tests: key derivation, nonce generation, encrypt/decrypt roundtrip,
    tampered-ciphertext rejection, and wrong-key rejection.

    Raises CryptoSelfTestFailed and aborts startup if any check fails.
    """
    try:
        # Key derivation
        salt = generate_salt()
        key = derive_master_key("vaultx-self-test-2025", salt)
        assert len(key) == KEY_SIZE, f"Expected key length {KEY_SIZE}, got {len(key)}"

        # Nonce generation
        nonce = generate_nonce()
        assert len(nonce) == NONCE_SIZE, f"Expected nonce length {NONCE_SIZE}, got {len(nonce)}"

        # Encrypt / decrypt roundtrip
        plaintext = b"VaultX cryptographic self-test payload."
        aad = b"vaultx-self-test-aad"
        ciphertext = encrypt_chunk(plaintext, key, nonce, aad)
        assert len(ciphertext) == len(plaintext) + TAG_SIZE, "Ciphertext length mismatch."
        recovered = decrypt_chunk(ciphertext, key, nonce, aad)
        assert recovered == plaintext, "Decrypted data does not match original plaintext."

        # Tampered ciphertext must be rejected
        tampered = bytearray(ciphertext)
        tampered[0] ^= 0xFF
        try:
            decrypt_chunk(bytes(tampered), key, nonce, aad)
            raise AssertionError("Tampered ciphertext was incorrectly accepted.")
        except AuthenticationFailed:
            pass

        # Wrong key must be rejected
        wrong_key = secrets.token_bytes(KEY_SIZE)
        try:
            decrypt_chunk(ciphertext, wrong_key, nonce, aad)
            raise AssertionError("Wrong key was incorrectly accepted.")
        except AuthenticationFailed:
            pass

        # Wrong AAD must be rejected
        try:
            decrypt_chunk(ciphertext, key, nonce, b"wrong-aad")
            raise AssertionError("Wrong AAD was incorrectly accepted.")
        except AuthenticationFailed:
            pass

        # SHA-256 determinism check
        h1 = compute_sha256(plaintext)
        h2 = compute_sha256(plaintext)
        assert h1 == h2, "SHA-256 is not deterministic."

    except CryptoSelfTestFailed:
        raise
    except Exception as exc:
        raise CryptoSelfTestFailed(
            f"Cryptographic self-test failed: {exc}"
        ) from exc
