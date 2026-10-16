"""LabVIEW's flattened EXT: the same value in 16 bytes, IEEE 754 binary128 layout.

LabVIEW 2026 on Windows flattens an EXT as one sign bit, the same 15-bit exponent
(bias 16383) and a 112-bit fraction with an implicit leading bit; the 63 fraction bits
of the 80-bit mantissa land at the top of the 112 (checked against LabVIEW's own
datalog records, tests/fixtures/labview2026). Widening is exact. Narrowing rounds the
113-bit significand once to 64 bits.
"""

from __future__ import annotations

from fractions import Fraction

from . import _codec
from ._errors import InvalidEncodingError
from ._kind import EXP_MAX, FRACTION_MASK, INT_BIT, ExtKind, classify
from ._rounding import Rounding

FLAT_FRACTION_BITS = 112
_SHIFT = FLAT_FRACTION_BITS - 63  # aligns the 63 fraction bits at the top of 112
_FLAT_FRACTION_MASK = (1 << FLAT_FRACTION_BITS) - 1
_LOST_MASK = (1 << _SHIFT) - 1
_FLAT_SCALE = _codec.EXP_BIAS + FLAT_FRACTION_BITS  # value = significand * 2**(e - this)

Triple = tuple[int, int, int]


def to_flat(sign: int, exponent: int, mantissa: int) -> int:
    """Return the 128-bit flattened pattern of an encoding; exact for every valid one.

    A pseudo-denormal is written with its value (exponent 1). The encodings the x87
    rejects have no value and raise InvalidEncodingError.
    """
    kind = classify(exponent, mantissa)
    if not kind.is_valid:
        raise InvalidEncodingError(f"{kind.value} encoding has no flattened form")
    if kind is ExtKind.PSEUDO_DENORMAL:
        exponent = 1
    fraction = (mantissa & FRACTION_MASK) << _SHIFT
    return (sign << 127) | (exponent << FLAT_FRACTION_BITS) | fraction


def from_flat(bits: int, mode: Rounding) -> Triple:
    """Return the (sign, exponent, mantissa) of a 128-bit flattened pattern.

    Finite values round once to 64 significant bits with ``mode`` and underflow
    gradually. A NaN keeps its sign, quiet bit and the top 62 payload bits; a signaling
    NaN whose payload sits only in the dropped bits keeps payload 1, so it stays a NaN.
    """
    sign = bits >> 127
    exponent = (bits >> FLAT_FRACTION_BITS) & EXP_MAX
    fraction = bits & _FLAT_FRACTION_MASK
    if exponent == EXP_MAX:
        if fraction == 0:
            return sign, EXP_MAX, INT_BIT
        return sign, EXP_MAX, INT_BIT | ((fraction >> _SHIFT) or 1)
    if fraction & _LOST_MASK == 0:
        if exponent == 0:
            return sign, 0, fraction >> _SHIFT
        return sign, exponent, INT_BIT | (fraction >> _SHIFT)
    significand = fraction | (1 << FLAT_FRACTION_BITS) if exponent else fraction
    scale = max(exponent, 1) - _FLAT_SCALE
    magnitude = Fraction(significand, 1 << -scale) if scale < 0 else Fraction(significand << scale)
    new_exponent, mantissa = _codec.from_magnitude(magnitude, sign == 1, mode)
    return sign, new_exponent, mantissa
