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
from ._rounding import Rounding, RoundingMode
from ._text import ByteOrder
from ._value import Ext80, Narrowed

__version__ = "1.0.0"

# Public classes report the package as their home, so reprs, tracebacks and pickles
# name ``lvext.Ext80`` rather than the private module that defines it.
for _public in (
    Ext80,
    ExtKind,
    InvalidEncodingError,
    LvextError,
    Narrowed,
    NotFiniteError,
    Rounding,
):
    _public.__module__ = __name__
del _public

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
    "RoundingMode",
    "pack_ext",
    "pack_ext128",
    "unpack_ext",
    "unpack_ext128",
]
