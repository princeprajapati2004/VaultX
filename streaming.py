"""Streaming per-file encryption and decryption for VaultX.

Each file is split into 64 KB chunks. Every chunk gets a fresh
random 24-byte nonce so that nonce reuse is physically impossible.
AAD = file_id_bytes + chunk_index (little-endian uint32) to prevent
cross-file or within-file chunk reordering attacks.

File (.vx) layout
-----------------
HEADER  8 bytes:
  magic[4]   = b"VXFL"
  version[1] = 1
  flags[1]   = bit-0: compressed with zlib
  reserved[2]= 0x00 0x00

CHUNKS  (repeated until EOF):
  nonce[24]          random XChaCha20 nonce for this chunk
  ciphertext_len[4]  LE uint32 — length of following ciphertext incl. 16-byte tag
  ciphertext[N]      XChaCha20-Poly1305 encrypted data (plaintext + tag appended)
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from pathlib import Path

from constants import (
    ALREADY_COMPRESSED_EXTENSIONS,
    CHUNK_SIZE,
    VX_MAGIC,
    VX_VERSION,
)
from crypto import NONCE_SIZE, decrypt_chunk, encrypt_chunk, generate_nonce
from exceptions import AuthenticationFailed, CorruptedVault

_HEADER_SIZE = 8
_FLAG_COMPRESSED: int = 0x01


def should_compress(file_path: Path) -> bool:
    """Return True when the file's extension benefits from zlib compression."""
    return file_path.suffix.lower() not in ALREADY_COMPRESSED_EXTENSIONS


def encrypt_file(
    source_path: Path,
    dest_path: Path,
    master_key: bytes,
    file_id: str,
    *,
    compress: bool | None = None,
) -> tuple[str, bool]:
    """
    Encrypt *source_path* → *dest_path* in 64 KB streaming chunks.

    Returns (sha256_hex_of_plaintext, was_compressed).
    The SHA-256 is computed over the original, uncompressed plaintext so it
    can be stored in metadata and verified on decryption.
    """
    if compress is None:
        compress = should_compress(source_path)

    file_id_bytes = file_id.encode("utf-8")
    hasher = hashlib.sha256()
    flags = _FLAG_COMPRESSED if compress else 0x00

    with source_path.open("rb") as src, dest_path.open("wb") as dst:
        dst.write(VX_MAGIC)
        dst.write(bytes([VX_VERSION, flags, 0x00, 0x00]))

        chunk_index = 0
        while True:
            chunk = src.read(CHUNK_SIZE)
            if not chunk:
                break

            # SHA-256 is computed on plaintext before any compression
            hasher.update(chunk)

            payload = zlib.compress(chunk, level=6) if compress else chunk

            nonce = generate_nonce()
            # AAD binds ciphertext to this specific file + chunk position
            aad = file_id_bytes + struct.pack("<I", chunk_index)
            ciphertext = encrypt_chunk(payload, master_key, nonce, aad)

            dst.write(nonce)
            dst.write(struct.pack("<I", len(ciphertext)))
            dst.write(ciphertext)
            chunk_index += 1

    return hasher.hexdigest(), compress


def decrypt_file(
    source_path: Path,
    dest_path: Path,
    master_key: bytes,
    file_id: str,
    *,
    expected_sha256: str | None = None,
) -> None:
    """
    Decrypt *source_path* → *dest_path* in 64 KB streaming chunks.

    Each chunk's Poly1305 tag is verified before writing any plaintext.
    If *expected_sha256* is provided the reconstructed plaintext is also
    verified against the stored SHA-256 from metadata.
    """
    file_id_bytes = file_id.encode("utf-8")
    hasher = hashlib.sha256()

    with source_path.open("rb") as src, dest_path.open("wb") as dst:
        header = src.read(_HEADER_SIZE)
        if len(header) < _HEADER_SIZE:
            raise CorruptedVault(f"File too short to contain a valid header: {source_path.name}")
        if header[:4] != VX_MAGIC:
            raise CorruptedVault(f"Invalid .vx magic bytes in {source_path.name}")
        if header[4] != VX_VERSION:
            raise CorruptedVault(
                f"Unsupported .vx version {header[4]} in {source_path.name}"
            )

        compressed = bool(header[5] & _FLAG_COMPRESSED)
        chunk_index = 0

        while True:
            nonce_bytes = src.read(NONCE_SIZE)
            if not nonce_bytes:
                break   # clean EOF after last chunk
            if len(nonce_bytes) < NONCE_SIZE:
                raise CorruptedVault(
                    f"Truncated nonce at chunk {chunk_index} in {source_path.name}"
                )

            size_bytes = src.read(4)
            if len(size_bytes) < 4:
                raise CorruptedVault(
                    f"Truncated chunk-size field at chunk {chunk_index} in {source_path.name}"
                )
            ciphertext_len = struct.unpack("<I", size_bytes)[0]

            ciphertext = src.read(ciphertext_len)
            if len(ciphertext) < ciphertext_len:
                raise CorruptedVault(
                    f"Truncated chunk {chunk_index} payload in {source_path.name}"
                )

            aad = file_id_bytes + struct.pack("<I", chunk_index)
            try:
                payload = decrypt_chunk(ciphertext, master_key, nonce_bytes, aad)
            except AuthenticationFailed:
                raise CorruptedVault(
                    f"Authentication failed for chunk {chunk_index} of {source_path.name}. "
                    "File may be tampered with or corrupted."
                )

            plaintext = zlib.decompress(payload) if compressed else payload
            hasher.update(plaintext)
            dst.write(plaintext)
            chunk_index += 1

    if expected_sha256 and hasher.hexdigest() != expected_sha256:
        raise CorruptedVault(
            f"SHA-256 mismatch for {source_path.name}. "
            "The decrypted content does not match the stored checksum."
        )
