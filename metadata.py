"""Encrypted metadata management for the VaultX per-file vault."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from constants import METADATA_FILE
from crypto import decrypt_chunk, encrypt_chunk, generate_nonce
from exceptions import MetadataCorrupted

# AAD used for metadata AEAD — binding ciphertext to its role
_METADATA_AAD = b"vaultx-metadata-v1"
METADATA_SCHEMA_VERSION = 1


@dataclass
class FileRecord:
    """Metadata entry describing one encrypted file stored in the vault."""

    file_id: str
    original_name: str
    encrypted_name: str          # "<file_id>.vx"
    size: int                    # plaintext byte count
    sha256: str                  # hex SHA-256 of plaintext before encryption
    created: str                 # ISO 8601 UTC
    modified: str                # ISO 8601 UTC
    encryption_version: int      # always 1 for XChaCha20-Poly1305 / Argon2id
    compressed: bool             # True when zlib was applied before encryption

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileRecord":
        return cls(**{k: data[k] for k in cls.__dataclass_fields__})


@dataclass
class VaultMetadata:
    """Full metadata index for all files stored in the vault."""

    version: int = METADATA_SCHEMA_VERSION
    vault_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    files: dict[str, FileRecord] = field(default_factory=dict)

    def add_file(self, record: FileRecord) -> None:
        self.files[record.file_id] = record

    def remove_file(self, file_id: str) -> None:
        self.files.pop(file_id, None)

    def get_file(self, file_id: str) -> FileRecord | None:
        return self.files.get(file_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "vault_id": self.vault_id,
            "files": {fid: rec.to_dict() for fid, rec in self.files.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VaultMetadata":
        files = {
            fid: FileRecord.from_dict(rec)
            for fid, rec in data.get("files", {}).items()
        }
        return cls(
            version=data.get("version", METADATA_SCHEMA_VERSION),
            vault_id=data.get("vault_id", str(uuid.uuid4())),
            files=files,
        )


def build_file_record(
    file_id: str,
    original_name: str,
    plaintext_path: Path,
    *,
    sha256: str,
    compressed: bool,
    encryption_version: int = 1,
) -> FileRecord:
    """Construct a FileRecord from a source file path and its computed SHA-256."""
    stat = plaintext_path.stat()
    created = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat()
    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    return FileRecord(
        file_id=file_id,
        original_name=original_name,
        encrypted_name=f"{file_id}.vx",
        size=stat.st_size,
        sha256=sha256,
        created=created,
        modified=modified,
        encryption_version=encryption_version,
        compressed=compressed,
    )


def encrypt_metadata(meta: VaultMetadata, master_key: bytes) -> bytes:
    """Serialize and encrypt the metadata index with XChaCha20-Poly1305."""
    plaintext = json.dumps(meta.to_dict(), indent=2, sort_keys=True).encode("utf-8")
    nonce = generate_nonce()
    ciphertext = encrypt_chunk(plaintext, master_key, nonce, _METADATA_AAD)
    # Layout: [nonce (24 bytes)][ciphertext + Poly1305 tag]
    return nonce + ciphertext


def decrypt_metadata(data: bytes, master_key: bytes) -> VaultMetadata:
    """Decrypt and deserialize the metadata index."""
    from crypto import NONCE_SIZE
    if len(data) <= NONCE_SIZE:
        raise MetadataCorrupted("Metadata blob is too short to contain a valid nonce.")
    nonce = data[:NONCE_SIZE]
    ciphertext = data[NONCE_SIZE:]
    try:
        plaintext = decrypt_chunk(ciphertext, master_key, nonce, _METADATA_AAD)
        return VaultMetadata.from_dict(json.loads(plaintext.decode("utf-8")))
    except Exception as exc:
        raise MetadataCorrupted(f"Metadata decryption failed: {exc}") from exc


def load_metadata(master_key: bytes) -> VaultMetadata:
    """Load and decrypt the vault metadata file from disk.

    Returns an empty VaultMetadata if no metadata file exists yet.
    """
    if not METADATA_FILE.exists():
        return VaultMetadata()
    try:
        data = METADATA_FILE.read_bytes()
        if not data:
            return VaultMetadata()
        return decrypt_metadata(data, master_key)
    except MetadataCorrupted:
        raise
    except Exception as exc:
        raise MetadataCorrupted(f"Failed to load vault metadata: {exc}") from exc


def save_metadata(meta: VaultMetadata, master_key: bytes) -> None:
    """Encrypt the metadata and write it atomically to disk."""
    encrypted = encrypt_metadata(meta, master_key)
    tmp_path = METADATA_FILE.with_suffix(".tmp")
    tmp_path.write_bytes(encrypted)
    tmp_path.replace(METADATA_FILE)
