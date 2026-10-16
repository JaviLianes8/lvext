"""Correct single rounding of an exact positive rational to a binary format."""

from __future__ import annotations

from enum import Enum
from fractions import Fraction
from typing import Literal

from ._errors import LvextError
from ._text import short


class Rounding(str, Enum):
    """The four x87 rounding control modes, also the four IEEE 754 binary modes.

    Wherever a mode is taken, its string value works too.

    >>> Ext80.from_fraction(Fraction(-1, 3), Rounding.FLOOR).hex()
    'bffdaaaaaaaaaaaaaaab'
    >>> Rounding("toward-zero") is Rounding.TOWARD_ZERO
    True
    """

    NEAREST_EVEN = "nearest-even"
    """Round to nearest, ties to even. The x87 and IEEE 754 default."""
    FLOOR = "floor"
    """Round toward minus infinity."""
    CEILING = "ceiling"
    """Round toward plus infinity."""
    TOWARD_ZERO = "toward-zero"
    """Truncate toward zero."""


RoundingName = Literal["nearest-even", "floor", "ceiling", "toward-zero"]
RoundingMode = Rounding | RoundingName
"""A Rounding member or its string value; both are accepted wherever a mode is."""


def _round_quotient(num: int, den: int, negative: bool, mode: Rounding) -> int:
    """Round the magnitude num/den to an integer for a value with the given sign."""
    quotient, remainder = divmod(num, den)
    if remainder == 0:
        return quotient
    if mode is Rounding.NEAREST_EVEN:
        twice = 2 * remainder
        up = twice > den or (twice == den and quotient & 1 == 1)
    elif mode is Rounding.TOWARD_ZERO:
        up = False
    elif mode is Rounding.CEILING:
        up = not negative
    else:
        up = negative
    return quotient + 1 if up else quotient


def _floor_log2(num: int, den: int) -> int:
    """Return floor(log2(num/den)) exactly for positive integers."""
    exp = num.bit_length() - den.bit_length()
    below = num < den << exp if exp >= 0 else num << -exp < den
    return exp - 1 if below else exp


def round_magnitude(
    magnitude: Fraction, negative: bool, precision: int, emin: int, mode: Rounding
) -> tuple[int, int]:
    """Round a positive magnitude to ``significand * 2**scale``, rounding once.

    The significand has at most ``precision`` bits. ``emin`` is the smallest unbiased
    exponent of a normal number; below it the scale is pinned and the result loses
    bits gradually (subnormal). The caller checks the top exponent for overflow.
    """
    num, den = magnitude.numerator, magnitude.denominator
    scale = max(_floor_log2(num, den), emin) - (precision - 1)
    if scale >= 0:
        significand = _round_quotient(num, den << scale, negative, mode)
    else:
        significand = _round_quotient(num << -scale, den, negative, mode)
    if significand >> precision:
        significand >>= 1
        scale += 1
    return significand, scale


def overflow_saturates(negative: bool, mode: Rounding) -> bool:
    """Return True when an overflow rounds to the largest finite value, not infinity."""
    if mode is Rounding.NEAREST_EVEN:
        return False
    if mode is Rounding.TOWARD_ZERO:
        return True
    if mode is Rounding.CEILING:
        return negative
    return not negative


def as_rounding(value: object) -> Rounding:
    """Return the Rounding for a member or its string value, else raise LvextError."""
    try:
        return Rounding(value)
    except ValueError:
        names = ", ".join(mode.value for mode in Rounding)
        raise LvextError(f"rounding must be one of {names}, got {short(value)}") from None
