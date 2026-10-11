"""Bit-level conversions between the 80-bit extended format, doubles and rationals.

An extended value is handled as three integers: the sign (0 or 1), the 15-bit biased
exponent and the 64-bit mantissa whose bit 63 is the explicit integer bit. A finite
encoding with exponent ``e`` and mantissa ``m`` has the value
``m * 2**(max(e, 1) - 16383 - 63)``.
"""

from __future__ import annotations

import math
import struct
import sys
from fractions import Fraction

from ._kind import EXP_MAX, FRACTION_MASK, INT_BIT, QUIET_BIT, ExtKind, classify
from ._rounding import Rounding, overflow_saturates, round_magnitude

EXP_BIAS = 16383
MANTISSA_MASK = (1 << 64) - 1
SCALE_OFFSET = EXP_BIAS + 63  # value = mantissa * 2**(max(e, 1) - SCALE_OFFSET)
EMIN = 1 - EXP_BIAS  # unbiased exponent of the smallest normal

_D_EXP_MASK = 0x7FF
_D_FRAC_BITS = 52
_D_FRAC_MASK = (1 << _D_FRAC_BITS) - 1
_D_QUIET = 1 << 51
_D_INDEFINITE = 0xFFF8000000000000  # the x87 "real indefinite" QNaN as a double
_SHIFT = 63 - _D_FRAC_BITS  # aligns a double fraction under the integer bit

Triple = tuple[int, int, int]


def double_bits(value: float) -> int:
    """Return the IEEE 754 binary64 bit pattern of a float."""
    return int(struct.unpack(">Q", struct.pack(">d", value))[0])


def bits_double(bits: int) -> float:
    """Return the float with this IEEE 754 binary64 bit pattern."""
    return float(struct.unpack(">d", struct.pack(">Q", bits))[0])


def from_double(value: float) -> Triple:
    """Encode a double exactly. A signaling NaN is quieted, as the x87 FLD does."""
    bits = double_bits(value)
    sign = bits >> 63
    exp = (bits >> _D_FRAC_BITS) & _D_EXP_MASK
    frac = bits & _D_FRAC_MASK
    if exp == _D_EXP_MASK:
        if frac == 0:
            return sign, EXP_MAX, INT_BIT
        return sign, EXP_MAX, INT_BIT | QUIET_BIT | (frac << _SHIFT)
    if exp == 0:
        if frac == 0:
            return sign, 0, 0
        # A subnormal double is frac * 2**-1074, well inside the extended normal
        # range: move its leading bit up to the integer bit and adjust the exponent.
        width = frac.bit_length()
        return sign, width + EXP_BIAS - 1075, frac << (64 - width)
    return sign, exp - 1023 + EXP_BIAS, INT_BIT | (frac << _SHIFT)


def magnitude(exponent: int, mantissa: int) -> Fraction:
    """Return the exact magnitude of a finite encoding."""
    scale = max(exponent, 1) - SCALE_OFFSET
    if scale >= 0:
        return Fraction(mantissa << scale)
    return Fraction(mantissa, 1 << -scale)


def from_magnitude(value: Fraction, negative: bool, mode: Rounding) -> tuple[int, int]:
    """Round a positive rational once to an (exponent, mantissa) pair."""
    significand, scale = round_magnitude(value, negative, 64, EMIN, mode)
    top = scale + 63
    if top > EXP_BIAS:
        if overflow_saturates(negative, mode):
            return EXP_MAX - 1, MANTISSA_MASK
        return EXP_MAX, INT_BIT
    if significand & INT_BIT:
        return top + EXP_BIAS, significand
    return 0, significand


def to_double(sign: int, exponent: int, mantissa: int, mode: Rounding) -> tuple[float, bool]:
    """Narrow an encoding to a double; return the double and whether it is exact.

    Finite values round once with ``mode`` and underflow gradually. NaN keeps its sign
    and the top 51 payload bits and comes out quiet. Encodings the x87 rejects give
    the x87 indefinite NaN, as FSTP does with the invalid exception masked.
    """
    kind = classify(exponent, mantissa)
    negative = sign == 1
    if not kind.is_valid:
        return bits_double(_D_INDEFINITE), False
    if kind is ExtKind.INFINITY:
        return (-math.inf if negative else math.inf), True
    if kind.is_nan:
        payload = (mantissa & FRACTION_MASK) >> _SHIFT
        bits = (sign << 63) | (_D_EXP_MASK << _D_FRAC_BITS) | _D_QUIET | payload
        exact = kind is ExtKind.QUIET_NAN and mantissa & ((1 << _SHIFT) - 1) == 0
        return bits_double(bits), exact
    if kind is ExtKind.ZERO:
        return (-0.0 if negative else 0.0), True
    exact_value = magnitude(exponent, mantissa)
    significand, scale = round_magnitude(exact_value, negative, 53, -1022, mode)
    if scale + 52 > 1023:
        result = sys.float_info.max if overflow_saturates(negative, mode) else math.inf
        return (-result if negative else result), False
    result = math.ldexp(significand, scale)
    exact = Fraction(significand) * Fraction(2) ** scale == exact_value
    return (-result if negative else result), exact
