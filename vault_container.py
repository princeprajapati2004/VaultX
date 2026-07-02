"""Vault container format (.vxdb) - binary sealed vault format."""

from __future__ import annotations

import os
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import secrets

from crypto import (
    derive_master_key,
    encrypt_chunk,
    decrypt_chunk,
    generate_nonce,
)


VXDB_MAGIC = b"VXDB"
VXDB_VERSION = 1

# Header structure offsets (all in bytes)
HEADER_MAGIC_OFFSET = 0
HEADER_MAGIC_SIZE = 4
HEADER_VERSION_OFFSET = HEADER_MAGIC_OFFSET + HEADER_MAGIC_SIZE
HEADER_VERSION_SIZE = 2
HEADER_SIZE_OFFSET = HEADER_VERSION_OFFSET + HEADER_VERSION_SIZE
HEADER_SIZE_SIZE = 2
HEADER_TOTAL_FIXED = HEADER_MAGIC_SIZE + HEADER_VERSION_SIZE + HEADER_SIZE_SIZE


@dataclass
class VaultHeader:
    """Binary vault container header."""

    vault_uuid: bytes  # 16 bytes
    created_timestamp: int  # Unix timestamp
    last_password_change: int  # Unix timestamp
    argon2_time_cost: int
    argon2_memory_cost: int
    argon2_parallelism: int
    salt: bytes  # 32 bytes
    encrypted_mek: bytes  # Encrypted master encryption key
    metadata_offset: int  # Where encrypted metadata begins in the file
    magic: bytes = VXDB_MAGIC
    version: int = VXDB_VERSION
    reserved: bytes = b""  # Reserved for future use

    def serialize(self) -> bytes:
        """Serialize header to binary format."""
        vault_uuid = self.vault_uuid if isinstance(self.vault_uuid, bytes) else self.vault_uuid.encode() if isinstance(self.vault_uuid, str) else b''
        if len(vault_uuid) != 16:
            vault_uuid = vault_uuid[:16].ljust(16, b'\x00')

        salt = self.salt if isinstance(self.salt, bytes) else self.salt.encode() if isinstance(self.salt, str) else b''
        if len(salt) != 32:
            salt = salt[:32].ljust(32, b'\x00')

        encrypted_mek = self.encrypted_mek if isinstance(self.encrypted_mek, bytes) else b''

        data = b""
        data += struct.pack("<4s", self.magic)  # Magic
        data += struct.pack("<H", self.version)  # Version
        data += struct.pack("<Q", self.created_timestamp)  # Created timestamp
        data += struct.pack("<Q", self.last_password_change)  # Last password change
        data += struct.pack("<I", self.argon2_time_cost)  # Argon2 time cost
        data += struct.pack("<I", self.argon2_memory_cost)  # Argon2 memory cost
        data += struct.pack("<I", self.argon2_parallelism)  # Argon2 parallelism
        data += struct.pack("<H", len(salt))  # Salt length
        data += salt  # Salt (variable length, serialized as 32)
        data += struct.pack("<H", len(encrypted_mek))  # Encrypted MEK length
        data += encrypted_mek  # Encrypted MEK (variable length)
        data += struct.pack("<I", self.metadata_offset)  # Metadata offset
        data += vault_uuid  # Vault UUID (16 bytes)

        # Calculate and prepend actual header size.
        # data already contains magic(4) + version(2) + all fields.
        # The final header prepends a 2-byte size field between version and the
        # field data, so the total grows by 2.
        header_size = len(data) + 2  # +2 for the size field itself
        header = struct.pack("<4s", self.magic)  # Magic (4)
        header += struct.pack("<H", self.version)  # Version (2)
        header += struct.pack("<H", header_size)  # Header size (2)
        header += data[4 + 2:]  # Fields after magic+version (skip the 6 bytes already re-emitted)

        return header

    @staticmethod
    def deserialize(data: bytes) -> VaultHeader:
        """Deserialize header from binary format."""
        if len(data) < HEADER_TOTAL_FIXED + 2:
            raise ValueError("Header data too short")

        magic = data[HEADER_MAGIC_OFFSET : HEADER_MAGIC_OFFSET + HEADER_MAGIC_SIZE]
        if magic != VXDB_MAGIC:
            raise ValueError(f"Invalid magic: {magic!r}")

        version = struct.unpack("<H", data[HEADER_VERSION_OFFSET : HEADER_VERSION_OFFSET + HEADER_VERSION_SIZE])[0]
        header_size = struct.unpack("<H", data[HEADER_SIZE_OFFSET : HEADER_SIZE_OFFSET + HEADER_SIZE_SIZE])[0]

        if len(data) < header_size:
            raise ValueError(f"Header incomplete: expected {header_size}, got {len(data)}")

        offset = HEADER_TOTAL_FIXED
        created_ts = struct.unpack("<Q", data[offset : offset + 8])[0]
        offset += 8
        last_pwd_change = struct.unpack("<Q", data[offset : offset + 8])[0]
        offset += 8
        arg2_time = struct.unpack("<I", data[offset : offset + 4])[0]
        offset += 4
        arg2_mem = struct.unpack("<I", data[offset : offset + 4])[0]
        offset += 4
        arg2_par = struct.unpack("<I", data[offset : offset + 4])[0]
        offset += 4
        salt_len = struct.unpack("<H", data[offset : offset + 2])[0]
        offset += 2
        salt = data[offset : offset + salt_len]
        offset += salt_len
        mek_len = struct.unpack("<H", data[offset : offset + 2])[0]
        offset += 2
        encrypted_mek = data[offset : offset + mek_len]
        offset += mek_len
        metadata_off = struct.unpack("<I", data[offset : offset + 4])[0]
        offset += 4
        vault_uuid = data[offset : offset + 16]

        # Reject headers with Argon2 params outside sane bounds so an attacker
        # cannot weaken the KDF by modifying the .vxdb file.
        if not (1 <= arg2_time <= 1000):
            raise ValueError(f"Argon2id time_cost out of range: {arg2_time}")
        if not (8 <= arg2_mem <= 4 * 1024 * 1024):  # 8 KiB … 4 GiB
            raise ValueError(f"Argon2id memory_cost out of range: {arg2_mem}")
        if not (1 <= arg2_par <= 64):
            raise ValueError(f"Argon2id parallelism out of range: {arg2_par}")
        if len(salt) < 16:
            raise ValueError(f"Salt too short: {len(salt)} bytes")

        return VaultHeader(
            vault_uuid=vault_uuid,
            created_timestamp=created_ts,
            last_password_change=last_pwd_change,
            argon2_time_cost=arg2_time,
            argon2_memory_cost=arg2_mem,
            argon2_parallelism=arg2_par,
            salt=salt,
            encrypted_mek=encrypted_mek,
            metadata_offset=metadata_off,
            magic=magic,
            version=version,
        )


class VaultContainer:
    """Manages the .vxdb vault container file."""

    def __init__(self, vault_path: Path):
        """Initialize vault container at the given path."""
        self.vault_path = Path(vault_path)
        self.header: Optional[VaultHeader] = None
        self.mek: Optional[bytes] = None  # Master Encryption Key (decrypted)

    def create(
        self,
        password: str,
        argon2_time_cost: int = 3,
        argon2_memory_cost: int = 65536,
        argon2_parallelism: int = 4,
    ) -> bytes:
        """
        Create a new vault container.
        Returns the generated Master Encryption Key (MEK).
        """
        # Generate MEK (random 256-bit key)
        mek = secrets.token_bytes(32)

        # Generate salt
        salt = secrets.token_bytes(32)

        # Derive Key Encryption Key (KEK) from password
        kek = derive_master_key(
            password,
            salt,
            time_cost=argon2_time_cost,
            memory_cost=argon2_memory_cost,
            parallelism=argon2_parallelism,
        )

        # Encrypt MEK with KEK using XChaCha20-Poly1305
        nonce = generate_nonce()
        encrypted_mek_with_tag = encrypt_chunk(mek, kek, nonce)

        # Store nonce with encrypted MEK (tag is already appended by encrypt_chunk)
        full_encrypted_mek = nonce + encrypted_mek_with_tag

        # Generate vault UUID
        vault_uuid = secrets.token_bytes(16)

        # Create header
        now = int(time.time())
        self.header = VaultHeader(
            vault_uuid=vault_uuid,
            created_timestamp=now,
            last_password_change=now,
            argon2_time_cost=argon2_time_cost,
            argon2_memory_cost=argon2_memory_cost,
            argon2_parallelism=argon2_parallelism,
            salt=salt,
            encrypted_mek=full_encrypted_mek,
            metadata_offset=0,  # Will be updated when metadata is added
        )

        # Store MEK in memory for further use
        self.mek = mek

        # Write header to disk
        header_bytes = self.header.serialize()
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)
        self.vault_path.write_bytes(header_bytes)

        return mek

    def unlock(self, password: str) -> bool:
        """
        Unlock the vault with the given password.
        Returns True if successful, False if password is wrong.
        """
        if not self.vault_path.exists():
            raise FileNotFoundError(f"Vault not found at {self.vault_path}")

        # Read header
        vault_data = self.vault_path.read_bytes()
        self.header = VaultHeader.deserialize(vault_data)

        # Derive KEK from password
        kek = derive_master_key(
            password,
            self.header.salt,
            time_cost=self.header.argon2_time_cost,
            memory_cost=self.header.argon2_memory_cost,
            parallelism=self.header.argon2_parallelism,
        )

        # Attempt to decrypt MEK
        encrypted_data = self.header.encrypted_mek
        if len(encrypted_data) < 24 + 32 + 16:  # nonce (24) + ciphertext (32) + Poly1305 tag (16)
            return False

        nonce = encrypted_data[:24]
        ciphertext_with_tag = encrypted_data[24:]

        try:
            self.mek = decrypt_chunk(ciphertext_with_tag, kek, nonce)
            return True
        except Exception:
            return False

    def change_password(self, old_password: str, new_password: str) -> bool:
        """
        Change vault password without re-encrypting files.
        Generates a fresh Argon2id salt and writes atomically.
        Returns True if successful.
        """
        if not self.unlock(old_password):
            return False

        if not self.mek:
            return False

        # Generate a NEW salt so the old KEK cannot be reused
        new_salt = secrets.token_bytes(32)

        new_kek = derive_master_key(
            new_password,
            new_salt,
            time_cost=self.header.argon2_time_cost,
            memory_cost=self.header.argon2_memory_cost,
            parallelism=self.header.argon2_parallelism,
        )

        # Re-encrypt MEK with new KEK using a fresh nonce
        new_nonce = generate_nonce()
        new_encrypted_mek_with_tag = encrypt_chunk(self.mek, new_kek, new_nonce)
        self.header.salt = new_salt
        self.header.encrypted_mek = new_nonce + new_encrypted_mek_with_tag
        self.header.last_password_change = int(time.time())

        # Atomic write: write to .tmp then rename so a crash cannot corrupt the vault
        header_bytes = self.header.serialize()
        tmp_path = self.vault_path.with_suffix(".tmp")
        tmp_path.write_bytes(header_bytes)
        tmp_path.replace(self.vault_path)

        return True

    def get_mek(self) -> Optional[bytes]:
        """Get the decrypted Master Encryption Key."""
        return self.mek

    def is_unlocked(self) -> bool:
        """Check if vault is currently unlocked."""
        return self.mek is not None

    def lock(self) -> None:
        """Lock the vault by clearing MEK from memory."""
        self.mek = None
        self.header = None
