"""The exact 80-bit extended value type."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from typing import NamedTuple

from . import _codec, _decimal
from ._bits import Encoding80
from ._errors import InvalidEncodingError, NotFiniteError, require
from ._kind import EXP_MAX, INT_BIT, ExtKind
from ._rounding import Rounding, as_rounding

Number = int | float | Fraction | Decimal


class Narrowed(NamedTuple):
    """A float narrowed from an Ext80, and whether it holds the same value.

    >>> Ext80.from_fraction(Fraction(1, 3)).narrow()
    Narrowed(value=0.3333333333333333, exact=False)
    """

    value: float
    exact: bool


class Ext80(Encoding80):
    """One x87 80-bit extended value, held bit for bit.

    ``exponent`` is the 15-bit biased exponent (bias 16383) and ``mantissa`` the
    64-bit significand whose bit 63 is the explicit integer bit. Every one of the
    2**80 encodings can be held, including the ones the x87 rejects. Equality
    compares bits, so ``+0 != -0``, a NaN equals itself and a pseudo-denormal is not
    equal to its ``canonical()`` form.

    >>> Ext80(negative=False, exponent=0x3FFF, mantissa=1 << 63).to_float()
    1.0
    """

    @classmethod
    def from_float(cls, value: float) -> Ext80:
        """Encode a float exactly; every double fits. Signaling NaNs come out quiet.

        An int is taken at its exact value and rounded to nearest-even only beyond
        64 significant bits, as ``from_fraction`` does.

        >>> Ext80.from_float(-2.5).hex()
        'c000a000000000000000'
        """
        require(value, (float, int), "value")
        if isinstance(value, int):
            return cls.from_fraction(value)
        sign, exponent, mantissa = _codec.from_double(float(value))
        return cls(sign == 1, exponent, mantissa)

    @classmethod
    def from_fraction(
        cls, value: Fraction | int, rounding: Rounding = Rounding.NEAREST_EVEN
    ) -> Ext80:
        """Round an exact rational once to the nearest encoding in ``rounding`` mode.

        >>> Ext80.from_fraction(Fraction(1, 3), Rounding.TOWARD_ZERO).hex()
        '3ffdaaaaaaaaaaaaaaaa'
        """
        require(value, (Fraction, int), "value")
        mode = as_rounding(rounding)
        exact = Fraction(value)
        negative = exact < 0
        if exact == 0:
            return cls(False, 0, 0)
        exponent, mantissa = _codec.from_magnitude(abs(exact), negative, mode)
        return cls(negative, exponent, mantissa)

    @classmethod
    def from_decimal(cls, value: Decimal, rounding: Rounding = Rounding.NEAREST_EVEN) -> Ext80:
        """Round a Decimal once. Signed zero, infinities, NaN and sNaN are kept.

        >>> Ext80.from_decimal(Decimal("0.1")).hex()
        '3ffbcccccccccccccccd'
        """
        require(value, (Decimal,), "value")
        mode = as_rounding(rounding)
        negative = value.is_signed()
        if value.is_nan():
            return cls(negative, EXP_MAX, _decimal.nan_mantissa(value))
        if value.is_infinite():
            return cls(negative, EXP_MAX, INT_BIT)
        if value.is_zero():
            return cls(negative, 0, 0)
        return cls.from_fraction(_decimal.bounded(value), mode)

    @classmethod
    def from_number(cls, value: Number, rounding: Rounding = Rounding.NEAREST_EVEN) -> Ext80:
        """Encode an int, float, Fraction or Decimal; floats are always exact.

        >>> Ext80.from_number(Fraction(1, 4)) == Ext80.from_float(0.25)
        True
        """
        require(value, (int, float, Fraction, Decimal), "value")
        mode = as_rounding(rounding)
        if isinstance(value, float):
            return cls.from_float(value)
        if isinstance(value, Decimal):
            return cls.from_decimal(value, mode)
        return cls.from_fraction(value, mode)

    def to_fraction(self) -> Fraction:
        """Return the exact value. Raises for infinities, NaN and rejected encodings.

        >>> Ext80.from_hex("3ffd8000000000000000").to_fraction()
        Fraction(1, 4)
        """
        kind = self.kind
        if not kind.is_valid:
            raise InvalidEncodingError(f"{kind.value} encoding has no value")
        if not kind.is_finite:
            raise NotFiniteError(f"{kind.value} has no exact rational value")
        value = _codec.magnitude(self.exponent, self.mantissa)
        return -value if self.negative else value

    def to_decimal(self) -> Decimal:
        """Return the exact value with every digit; infinities and NaNs map across.

        >>> Ext80.from_float(0.1).to_decimal()
        Decimal('0.1000000000000000055511151231257827021181583404541015625')
        """
        kind = self.kind
        if kind is ExtKind.INFINITY or kind.is_nan:
            return _decimal.special_decimal(self.negative, kind, self.mantissa)
        return _decimal.exact_decimal(self.negative, abs(self.to_fraction()))

    def narrow(self, rounding: Rounding = Rounding.NEAREST_EVEN) -> Narrowed:
        """Round to a float in ``rounding`` mode and report whether it is exact.

        >>> Ext80.from_float(0.5).narrow()
        Narrowed(value=0.5, exact=True)
        """
        value, exact = _codec.to_double(
            int(self.negative), self.exponent, self.mantissa, as_rounding(rounding)
        )
        return Narrowed(value, exact)

    def to_float(self, rounding: Rounding = Rounding.NEAREST_EVEN) -> float:
        """Round to the nearest float (or as ``rounding`` says), as x87 FSTP does.

        >>> Ext80.from_fraction(Fraction(1, 3)).to_float(Rounding.CEILING)
        0.33333333333333337
        """
        return self.narrow(rounding).value
