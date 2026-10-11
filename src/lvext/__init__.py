"""Pack and unpack LabVIEW/x87 80-bit extended-precision floats in pure Python."""

from __future__ import annotations

from ._ext import ByteOrder, pack_ext, pack_ext128, unpack_ext, unpack_ext128

__version__ = "0.1.0"

__all__ = ["ByteOrder", "pack_ext", "pack_ext128", "unpack_ext", "unpack_ext128"]
