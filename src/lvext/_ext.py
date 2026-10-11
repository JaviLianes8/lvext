"""Bit-exact codec for the x87/LabVIEW 80-bit extended-precision float."""

from __future__ import annotations

import math
import struct
from typing import Literal

ByteOrder = Literal["big", "little"]

_EXP_BIAS = 16383
_EXP_MAX = 0x7FFF
_INT_BIT = 1 << 63
_QUIET_BIT = 1 << 62
_MANT_MASK = (1 << 64) - 1
_FRAC63_MASK = (1 << 63) - 1

# A Python float is an IEEE-754 double: 1 sign bit, an 11-bit exponent biased by
# 1023, and a 52-bit fraction with an implicit leading 1. The extended format has
# an explicit 64-bit mantissa (bit 63 is the integer bit) and a 15-bit exponent.
_DOUBLE_EXP_MASK = 0x7FF
_DOUBLE_FRAC_MASK = (1 << 52) - 1
_FRAC_SHIFT = 63 - 52  # line the double fraction up under the integer bit


def _encode(value: float) -> int:
    """Return the 80-bit extended representation of a double as an integer."""
    bits = int(struct.unpack(">Q", struct.pack(">d", value))[0])
    sign = bits >> 63
    exp = (bits >> 52) & _DOUBLE_EXP_MASK
    frac = bits & _DOUBLE_FRAC_MASK
    if exp == _DOUBLE_EXP_MASK:
        mant = _INT_BIT if frac == 0 else _INT_BIT | _QUIET_BIT | (frac << _FRAC_SHIFT)
        exp15 = _EXP_MAX
    elif exp == 0:
        if frac == 0:
            return sign << 79
        # A subnormal double is frac * 2**-1074 and fits inside the extended
        # normal range, so shift its leading bit up to the integer bit and offset
        # the exponent to match (1075 = the -1074 scale plus the one-bit shift).
        width = frac.bit_length()
        mant = frac << (64 - width)
        exp15 = width + (_EXP_BIAS - 1075)
    else:
        mant = _INT_BIT | (frac << _FRAC_SHIFT)
        exp15 = exp - 1023 + _EXP_BIAS
    return (sign << 79) | (exp15 << 64) | mant


def _decode(value80: int) -> float:
    """Return the double nearest to an 80-bit extended value held as an integer."""
    sign = value80 >> 79
    exp15 = (value80 >> 64) & _EXP_MAX
    mant = value80 & _MANT_MASK
    negative = sign == 1
    if exp15 == _EXP_MAX:
        if mant & _FRAC63_MASK:
            return math.nan
        return -math.inf if negative else math.inf
    if exp15 == 0 and mant == 0:
        return -0.0 if negative else 0.0
    try:
        result = math.ldexp(float(mant), exp15 - _EXP_BIAS - 63)
    except OverflowError:
        result = math.inf
    return -result if negative else result


def pack_ext(value: float, byteorder: ByteOrder = "big") -> bytes:
    """Pack a float into the 10-byte extended form (big-endian as LabVIEW flattens)."""
    return _encode(value).to_bytes(10, byteorder)


def unpack_ext(data: bytes, byteorder: ByteOrder = "big") -> float:
    """Unpack a 10-byte extended value into the nearest float."""
    if len(data) != 10:
        raise ValueError(f"extended value must be 10 bytes, got {len(data)}")
    return _decode(int.from_bytes(data, byteorder))


def pack_ext128(value: float, byteorder: ByteOrder = "big") -> bytes:
    """Pack a float into the 16-byte padded storage form, the value in the low 80 bits."""
    return _encode(value).to_bytes(16, byteorder)


def unpack_ext128(data: bytes, byteorder: ByteOrder = "big") -> float:
    """Unpack a 16-byte padded extended value, ignoring the padding bits."""
    if len(data) != 16:
        raise ValueError(f"padded extended value must be 16 bytes, got {len(data)}")
    return _decode(int.from_bytes(data, byteorder) & ((1 << 80) - 1))
