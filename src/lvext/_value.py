"""The exact 80-bit extended value type."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Literal, NamedTuple

from . import _codec, _decimal
from ._errors import InvalidEncodingError, LvextError, NotFiniteError, require
from ._kind import EXP_MAX, INT_BIT, ExtKind, classify
from ._rounding import Rounding, as_rounding

ByteOrder = Literal["big", "little"]
Bytes = bytes | bytearray | memoryview
Number = int | float | Fraction | Decimal


class Narrowed(NamedTuple):
    """A float narrowed from an Ext80, and whether it holds the same value."""

    value: float
    exact: bool


def check_order(byteorder: str) -> ByteOrder:
    """Return the byte order unchanged, or raise LvextError if it is unknown."""
    if byteorder == "big":
        return "big"
    if byteorder == "little":
        return "little"
    raise LvextError(f"byteorder must be 'big' or 'little', got {byteorder!r}")


def clean_hex(text: str) -> str:
    """Drop whitespace, underscores and a ``0x`` prefix from a hex string."""
    require(text, (str,), "hex text")
    cleaned = "".join(text.split()).replace("_", "")
    return cleaned[2:] if cleaned[:2].lower() == "0x" else cleaned


@dataclass(frozen=True)
class Ext80:
    """One x87 80-bit extended value, held bit for bit.

    ``exponent`` is the 15-bit biased exponent (bias 16383) and ``mantissa`` the
    64-bit significand whose bit 63 is the explicit integer bit. Every one of the
    2**80 encodings can be held, including the ones the x87 rejects. Equality
    compares bits, so ``+0 != -0``, a NaN equals itself and a pseudo-denormal is not
    equal to its ``canonical()`` form.
    """

    negative: bool
    exponent: int
    mantissa: int

    def __post_init__(self) -> None:
        if not isinstance(self.negative, bool):
            raise LvextError("negative must be a bool")
        require(self.exponent, (int,), "exponent")
        require(self.mantissa, (int,), "mantissa")
        if not 0 <= self.exponent <= EXP_MAX:
            raise LvextError(f"exponent must be an int in 0..{EXP_MAX}, got {self.exponent!r}")
        if not 0 <= self.mantissa <= _codec.MANTISSA_MASK:
            raise LvextError(f"mantissa must be an int in 0..2**64-1, got {self.mantissa!r}")

    def __repr__(self) -> str:
        return (
            f"Ext80(negative={self.negative}, exponent={self.exponent:#06x}, "
            f"mantissa={self.mantissa:#018x})"
        )

    @classmethod
    def from_int(cls, bits: int) -> Ext80:
        """Build from the 80-bit pattern as an integer (sign in bit 79)."""
        require(bits, (int,), "bits")
        if not 0 <= bits < 1 << 80:
            raise LvextError("an 80-bit pattern must be in 0..2**80-1")
        return cls(bool(bits >> 79), (bits >> 64) & EXP_MAX, bits & _codec.MANTISSA_MASK)

    def to_int(self) -> int:
        """Return the 80-bit pattern as an integer (sign in bit 79)."""
        return (int(self.negative) << 79) | (self.exponent << 64) | self.mantissa

    @classmethod
    def from_bytes(cls, data: Bytes, byteorder: ByteOrder = "big") -> Ext80:
        """Build from exactly 10 bytes. x87 memory order is ``"little"``."""
        require(data, (bytes, bytearray, memoryview), "data")
        raw = bytes(data)
        if len(raw) != 10:
            raise LvextError(f"extended value must be 10 bytes, got {len(raw)}")
        return cls.from_int(int.from_bytes(raw, check_order(byteorder)))

    def to_bytes(self, byteorder: ByteOrder = "big") -> bytes:
        """Return the 10-byte encoding in the given byte order."""
        return self.to_int().to_bytes(10, check_order(byteorder))

    @classmethod
    def from_hex(cls, text: str, byteorder: ByteOrder = "big") -> Ext80:
        """Build from 20 hex digits; whitespace, underscores and ``0x`` are allowed."""
        cleaned = clean_hex(text)
        if len(cleaned) != 20:
            raise LvextError(f"expected 20 hex digits, got {len(cleaned)}")
        try:
            raw = bytes.fromhex(cleaned)
        except ValueError:
            raise LvextError(f"not a hex string: {text!r}") from None
        return cls.from_bytes(raw, byteorder)

    def hex(self, byteorder: ByteOrder = "big") -> str:
        """Return the 10-byte encoding as 20 lowercase hex digits."""
        return self.to_bytes(byteorder).hex()

    @classmethod
    def from_float(cls, value: float) -> Ext80:
        """Encode a float exactly; every double fits. Signaling NaNs come out quiet."""
        require(value, (float, int), "value")
        sign, exponent, mantissa = _codec.from_double(float(value))
        return cls(sign == 1, exponent, mantissa)

    @classmethod
    def from_fraction(
        cls, value: Fraction | int, rounding: Rounding = Rounding.NEAREST_EVEN
    ) -> Ext80:
        """Round an exact rational once to the nearest encoding in ``rounding`` mode."""
        require(value, (Fraction, int), "value")
        exact = Fraction(value)
        negative = exact < 0
        if exact == 0:
            return cls(False, 0, 0)
        exponent, mantissa = _codec.from_magnitude(abs(exact), negative, as_rounding(rounding))
        return cls(negative, exponent, mantissa)

    @classmethod
    def from_decimal(cls, value: Decimal, rounding: Rounding = Rounding.NEAREST_EVEN) -> Ext80:
        """Round a Decimal once. Signed zero, infinities, NaN and sNaN are kept."""
        require(value, (Decimal,), "value")
        negative = value.is_signed()
        if value.is_nan():
            return cls(negative, EXP_MAX, _decimal.nan_mantissa(value))
        if value.is_infinite():
            return cls(negative, EXP_MAX, INT_BIT)
        if value.is_zero():
            return cls(negative, 0, 0)
        return cls.from_fraction(_decimal.bounded(value), rounding)

    @classmethod
    def from_number(cls, value: Number, rounding: Rounding = Rounding.NEAREST_EVEN) -> Ext80:
        """Encode an int, float, Fraction or Decimal; floats are always exact."""
        require(value, (int, float, Fraction, Decimal), "value")
        if isinstance(value, float):
            return cls.from_float(value)
        if isinstance(value, Decimal):
            return cls.from_decimal(value, rounding)
        return cls.from_fraction(value, rounding)

    @property
    def kind(self) -> ExtKind:
        """The class of this encoding."""
        return classify(self.exponent, self.mantissa)

    def to_fraction(self) -> Fraction:
        """Return the exact value. Raises for infinities, NaN and rejected encodings."""
        kind = self.kind
        if not kind.is_valid:
            raise InvalidEncodingError(f"{kind.value} encoding has no value")
        if not kind.is_finite:
            raise NotFiniteError(f"{kind.value} has no exact rational value")
        value = _codec.magnitude(self.exponent, self.mantissa)
        return -value if self.negative else value

    def to_decimal(self) -> Decimal:
        """Return the exact value with every digit; infinities and NaNs map across."""
        kind = self.kind
        if kind is ExtKind.INFINITY or kind.is_nan:
            return _decimal.special_decimal(self.negative, kind, self.mantissa)
        return _decimal.exact_decimal(self.negative, abs(self.to_fraction()))

    def narrow(self, rounding: Rounding = Rounding.NEAREST_EVEN) -> Narrowed:
        """Round to a float in ``rounding`` mode and report whether it is exact."""
        value, exact = _codec.to_double(
            int(self.negative), self.exponent, self.mantissa, as_rounding(rounding)
        )
        return Narrowed(value, exact)

    def to_float(self, rounding: Rounding = Rounding.NEAREST_EVEN) -> float:
        """Round to the nearest float (or as ``rounding`` says), as x87 FSTP does."""
        return self.narrow(rounding).value

    def canonical(self) -> Ext80:
        """Return the canonical encoding: a pseudo-denormal becomes exponent 1."""
        if self.kind is ExtKind.PSEUDO_DENORMAL:
            return Ext80(self.negative, 1, self.mantissa)
        return self
