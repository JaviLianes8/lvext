"""Classification of every 80-bit extended encoding (Intel SDM Vol. 1, 8.2.2)."""

from __future__ import annotations

from enum import Enum

EXP_MAX = 0x7FFF
INT_BIT = 1 << 63
QUIET_BIT = 1 << 62
FRACTION_MASK = INT_BIT - 1


class ExtKind(str, Enum):
    """What an 80-bit extended encoding represents.

    >>> Ext80.from_hex("3fff0000000000000000").kind
    <ExtKind.UNNORMAL: 'unnormal'>
    >>> ExtKind.UNNORMAL.is_valid, ExtKind.SUBNORMAL.is_finite, ExtKind.QUIET_NAN.is_nan
    (False, True, True)
    """

    ZERO = "zero"
    SUBNORMAL = "subnormal"
    NORMAL = "normal"
    INFINITY = "infinity"
    QUIET_NAN = "quiet-nan"
    SIGNALING_NAN = "signaling-nan"
    PSEUDO_DENORMAL = "pseudo-denormal"
    """Exponent 0 with the integer bit set. Loaded by the x87 with exponent 1."""
    UNNORMAL = "unnormal"
    """Exponent 1..32766 with the integer bit clear. Invalid since the 80387."""
    PSEUDO_INFINITY = "pseudo-infinity"
    """Exponent 32767, integer bit clear, fraction 0. Invalid since the 80387."""
    PSEUDO_NAN = "pseudo-nan"
    """Exponent 32767, integer bit clear, fraction not 0. Invalid since the 80387."""

    @property
    def is_valid(self) -> bool:
        """True unless the 80387 and later reject the encoding as an invalid operand."""
        return self not in _INVALID

    @property
    def is_finite(self) -> bool:
        """True for zero, subnormal, normal and pseudo-denormal encodings."""
        return self in _FINITE

    @property
    def is_nan(self) -> bool:
        """True for quiet and signaling NaN."""
        return self in (ExtKind.QUIET_NAN, ExtKind.SIGNALING_NAN)


_INVALID = frozenset({ExtKind.UNNORMAL, ExtKind.PSEUDO_INFINITY, ExtKind.PSEUDO_NAN})
_FINITE = frozenset({ExtKind.ZERO, ExtKind.SUBNORMAL, ExtKind.NORMAL, ExtKind.PSEUDO_DENORMAL})


def classify(exponent: int, mantissa: int) -> ExtKind:
    """Return the kind of the encoding with this biased exponent and 64-bit mantissa."""
    integer_bit = bool(mantissa & INT_BIT)
    fraction = mantissa & FRACTION_MASK
    if exponent == 0:
        if integer_bit:
            return ExtKind.PSEUDO_DENORMAL
        return ExtKind.SUBNORMAL if fraction else ExtKind.ZERO
    if exponent == EXP_MAX:
        if not integer_bit:
            return ExtKind.PSEUDO_NAN if fraction else ExtKind.PSEUDO_INFINITY
        if fraction == 0:
            return ExtKind.INFINITY
        return ExtKind.QUIET_NAN if mantissa & QUIET_BIT else ExtKind.SIGNALING_NAN
    return ExtKind.NORMAL if integer_bit else ExtKind.UNNORMAL
