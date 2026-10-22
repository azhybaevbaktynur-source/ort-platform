"""Safe read-only view of an uploaded zip (copy of the frozen bundle_service._SafeZip, limits from settings)."""
from __future__ import annotations

import io
import posixpath
import re
import zipfile
from typing import Any

from app.core.config import settings

JUNK_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}


class BundleError(Exception):
    """Fatal problem with the zip itself (nothing else can be checked)."""

    def __init__(self, code: str, message: str, **params: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.params = params


def _mb(n: int) -> int:
    return n // (1024 * 1024)


class SafeZip:
    def __init__(self, data: bytes):
        max_up = settings.IMPORT_MAX_UPLOAD_BYTES
        max_unc = settings.IMPORT_MAX_UNCOMPRESSED_BYTES
        max_entries = settings.IMPORT_MAX_ZIP_ENTRIES
        if len(data) > max_up:
            raise BundleError("zip_too_large", f"The zip is larger than {_mb(max_up)} MB.", limit_mb=_mb(max_up))
        try:
            self._zf = zipfile.ZipFile(io.BytesIO(data))
            infos = self._zf.infolist()
        except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError) as e:
            raise BundleError("zip_invalid", f"The file is not a valid zip archive ({e}).")

        if len(infos) > max_entries:
            raise BundleError("zip_too_many_files", f"The zip contains more than {max_entries} files.", limit=max_entries)
        if sum(i.file_size for i in infos) > max_unc:
            raise BundleError("zip_too_large", f"The zip unpacks to more than {_mb(max_unc)} MB.", limit_mb=_mb(max_unc))

        self.entries: dict[str, zipfile.ZipInfo] = {}
        for info in infos:
            name = info.filename.replace("\\", "/")
            parts = [p for p in name.split("/") if p not in ("", ".")]
            if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in parts or "\x00" in name:
                raise BundleError("zip_unsafe_path", f"Unsafe path in zip: '{info.filename}'.", path=info.filename)
            if info.is_dir() or not parts:
                continue
            base = parts[-1]
            if "__MACOSX" in parts or base.startswith("._") or base.lower() in JUNK_NAMES:
                continue
            if info.flag_bits & 0x1:
                raise BundleError("zip_encrypted", f"Encrypted file in zip: '{info.filename}'.", path=info.filename)
            self.entries["/".join(parts)] = info

        self._cache: dict[str, bytes] = {}

    def read(self, path: str) -> bytes:
        if path not in self._cache:
            info = self.entries[path]
            try:
                with self._zf.open(info) as f:
                    data = f.read(info.file_size + 1)
            except (zipfile.BadZipFile, RuntimeError, OSError, NotImplementedError) as e:
                raise BundleError("zip_invalid", f"Cannot read '{path}' from the zip ({e}).", path=path)
            if len(data) > info.file_size:
                raise BundleError("zip_invalid", f"Size mismatch for '{path}' in zip.", path=path)
            self._cache[path] = data
        return self._cache[path]

    def drop(self, path: str) -> None:
        self._cache.pop(path, None)

    def files_named(self, base_name: str) -> list[str]:
        low = base_name.lower()
        return [p for p in self.entries if posixpath.basename(p).lower() == low]
