"""Archive helpers for VaultX."""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path


def folder_to_bytes(folder_path: str | Path) -> bytes:
    """Compress a folder into an in-memory ZIP archive."""

    source_folder = Path(folder_path)
    memory = io.BytesIO()

    with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for full_path in source_folder.rglob("*"):
            if full_path.is_file():
                zip_file.write(full_path, full_path.relative_to(source_folder))

    memory.seek(0)
    return memory.read()


def bytes_to_folder(data: bytes, output_folder: str | Path) -> None:
    """Extract an in-memory ZIP archive into a folder with path validation."""

    output_path = Path(output_folder).resolve()
    memory = io.BytesIO(data)

    with zipfile.ZipFile(memory, "r") as zip_file:
        for member in zip_file.namelist():
            member_path = (output_path / member).resolve()

            if not str(member_path).startswith(str(output_path)):
                raise ValueError(f"Attempted path traversal: {member}")

            if os.path.isabs(member) or member.startswith(("../", "..\\", "~")):
                raise ValueError(f"Absolute or traversal path in archive: {member}")

            zip_file.extract(member, output_path)


def is_valid_zip_bytes(data: bytes) -> bool:
    """Return True when the supplied bytes are a valid ZIP archive."""

    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as zip_file:
            return zip_file.testzip() is None
    except zipfile.BadZipFile:
        return False