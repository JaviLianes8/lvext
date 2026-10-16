"""Exact conversions between Decimal and the 80-bit extended format."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

from ._errors import LvextError
from ._kind import INT_BIT, QUIET_BIT, ExtKind

_MAX_PAYLOAD_DIGITS = 19  # 2**62 - 1 has 19 decimal digits
# Every point where rounding to 64 bits changes (a 65-bit dyadic rational inside the
# range) has fewer than 11,600 significant decimal digits, so digits beyond this many
# only matter as "zero or not" and are folded into one sticky digit.
_KEEP_DIGITS = 12_000


def bounded(value: Decimal) -> Fraction:
    """Return the exact value of a finite Decimal, or a stand-in that rounds alike.

    Far outside the extended range every value rounds the same way in every mode,
    so an exponent such as ``1e999999999`` is never expanded into a huge integer.
    """
    sign = -1 if value.is_signed() else 1
    if value.adjusted() > 4940:
        return Fraction(sign * 2**16400)
    if value.adjusted() < -4960:
        return Fraction(sign, 2**16500)
    negative, digits, exponent = value.as_tuple()
    if len(digits) > _KEEP_DIGITS:
        assert isinstance(exponent, int)
        dropped = len(digits) - _KEEP_DIGITS
        kept = digits[:_KEEP_DIGITS]
        if any(digits[_KEEP_DIGITS:]):
            kept, dropped = (*kept, 1), dropped - 1
        value = Decimal((negative, kept, exponent + dropped))
    return Fraction(value)


def nan_mantissa(value: Decimal) -> int:
    """Return the mantissa for a Decimal NaN; its payload goes in the low 62 bits."""
    digits = value.as_tuple().digits
    if len(digits) > _MAX_PAYLOAD_DIGITS:
        raise LvextError("NaN payload does not fit in 62 bits")
    payload = int("".join(map(str, digits))) if digits else 0
    if payload >= QUIET_BIT:
        raise LvextError("NaN payload does not fit in 62 bits")
    if value.is_snan():
        return INT_BIT | (payload or 1)
    return INT_BIT | QUIET_BIT | payload


def special_decimal(negative: bool, kind: ExtKind, mantissa: int) -> Decimal:
    """Return the Decimal infinity or NaN (with payload) for a non-finite encoding."""
    sign = "-" if negative else ""
    if kind is ExtKind.INFINITY:
        return Decimal(f"{sign}Infinity")
    payload = mantissa & (QUIET_BIT - 1)
    prefix = "NaN" if kind is ExtKind.QUIET_NAN else "sNaN"
    return Decimal(f"{sign}{prefix}{payload or ''}")


def exact_decimal(negative: bool, magnitude: Fraction) -> Decimal:
    """Return a dyadic magnitude as a Decimal holding every digit, never rounded."""
    power = magnitude.denominator.bit_length() - 1
    digits = Decimal(magnitude.numerator * 5**power).as_tuple().digits
    return Decimal((int(negative), digits, -power))
