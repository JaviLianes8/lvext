"""Exact codec for the x87 80-bit extended-precision float, in pure Python."""

from __future__ import annotations

from ._errors import InvalidEncodingError, LvextError, NotFiniteError
from ._ext import pack_ext, pack_ext128, unpack_ext, unpack_ext128
from ._kind import ExtKind
from ._limits import (
    EXT80_EPSILON,
    EXT80_INDEFINITE,
    EXT80_MAX,
    EXT80_MIN_NORMAL,
    EXT80_MIN_SUBNORMAL,
)
from ._rounding import Rounding
from ._value import ByteOrder, Ext80, Narrowed

__version__ = "0.2.0"

__all__ = [
    "EXT80_EPSILON",
    "EXT80_INDEFINITE",
    "EXT80_MAX",
    "EXT80_MIN_NORMAL",
    "EXT80_MIN_SUBNORMAL",
    "ByteOrder",
    "Ext80",
    "ExtKind",
    "InvalidEncodingError",
    "LvextError",
    "Narrowed",
    "NotFiniteError",
    "Rounding",
    "pack_ext",
    "pack_ext128",
    "unpack_ext",
    "unpack_ext128",
]
