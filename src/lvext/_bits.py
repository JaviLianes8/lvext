"""The bit-level half of Ext80: fields, integers, bytes, hex and LabVIEW's 16-byte form."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

from . import _codec, _flat
from ._errors import LvextError, require
from ._kind import EXP_MAX, ExtKind, classify
from ._rounding import Rounding, RoundingMode, as_rounding
from ._text import ByteOrder, check_order, parse_hex, short

Bytes = bytes | bytearray | memoryview
_T = TypeVar("_T", bound="Encoding80")


@dataclass(frozen=True)
class Encoding80:
    """The three fields of an 80-bit extended encoding; Ext80 adds the numeric side."""

    negative: bool
    exponent: int
    mantissa: int

    def __post_init__(self) -> None:
        if not isinstance(self.negative, bool):
            raise LvextError("negative must be a bool")
        require(self.exponent, (int,), "exponent")
        require(self.mantissa, (int,), "mantissa")
        if not 0 <= self.exponent <= EXP_MAX:
            raise LvextError(f"exponent must be an int in 0..{EXP_MAX}, got {short(self.exponent)}")
        if not 0 <= self.mantissa <= _codec.MANTISSA_MASK:
            raise LvextError(f"mantissa must be an int in 0..2**64-1, got {short(self.mantissa)}")

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(negative={self.negative}, exponent={self.exponent:#06x}, "
            f"mantissa={self.mantissa:#018x})"
        )

    @classmethod
    def from_int(cls: type[_T], bits: int) -> _T:
        """Build from the 80-bit pattern as an integer (sign in bit 79).

        >>> Ext80.from_int(0x3FFF8000000000000000).to_float()
        1.0
        """
        require(bits, (int,), "bits")
        if not 0 <= bits < 1 << 80:
            raise LvextError("an 80-bit pattern must be in 0..2**80-1")
        return cls(bool(bits >> 79), (bits >> 64) & EXP_MAX, bits & _codec.MANTISSA_MASK)

    def to_int(self) -> int:
        """Return the 80-bit pattern as an integer (sign in bit 79).

        >>> hex(Ext80.from_float(-2.0).to_int())
        '0xc0008000000000000000'
        """
        return (int(self.negative) << 79) | (self.exponent << 64) | self.mantissa

    @classmethod
    def from_bytes(cls: type[_T], data: Bytes, byteorder: ByteOrder = "big") -> _T:
        """Build from exactly 10 bytes. x87 memory order is ``"little"``.

        >>> Ext80.from_bytes(bytes.fromhex("0000000000000080ff3f"), "little").to_float()
        1.0
        """
        require(data, (bytes, bytearray, memoryview), "data")
        raw = bytes(data)
        if len(raw) != 10:
            raise LvextError(f"extended value must be 10 bytes, got {len(raw)}")
        return cls.from_int(int.from_bytes(raw, check_order(byteorder)))

    def to_bytes(self, byteorder: ByteOrder = "big") -> bytes:
        """Return the 10-byte encoding in the given byte order.

        >>> Ext80.from_float(1.0).to_bytes("little").hex()
        '0000000000000080ff3f'
        """
        return self.to_int().to_bytes(10, check_order(byteorder))

    @classmethod
    def from_hex(cls: type[_T], text: str, byteorder: ByteOrder = "big") -> _T:
        """Build from 20 hex digits; whitespace, underscores and ``0x`` are allowed.

        >>> Ext80.from_hex("4000 c90f daa2 2168 c235").kind.value
        'normal'
        """
        return cls.from_bytes(parse_hex(text, 20), byteorder)

    def hex(self, byteorder: ByteOrder = "big") -> str:
        """Return the 10-byte encoding as 20 lowercase hex digits.

        >>> Ext80.from_float(0.25).hex()
        '3ffd8000000000000000'
        """
        return self.to_bytes(byteorder).hex()

    @classmethod
    def from_flattened(
        cls: type[_T],
        data: Bytes,
        byteorder: ByteOrder = "big",
        rounding: RoundingMode = Rounding.NEAREST_EVEN,
    ) -> _T:
        """Read LabVIEW's 16-byte flattened EXT, rounding once to 64 bits if needed.

        LabVIEW flattens big-endian. NaN keeps its sign, quiet bit and top payload bits.

        >>> Ext80.from_flattened(bytes.fromhex("3fff" + "00" * 14)).to_float()
        1.0
        """
        require(data, (bytes, bytearray, memoryview), "data")
        raw = bytes(data)
        if len(raw) != 16:
            raise LvextError(f"flattened EXT must be 16 bytes, got {len(raw)}")
        mode = as_rounding(rounding)
        sign, exponent, mantissa = _flat.from_flat(
            int.from_bytes(raw, check_order(byteorder)), mode
        )
        return cls(sign == 1, exponent, mantissa)

    def to_flattened(self, byteorder: ByteOrder = "big") -> bytes:
        """Return LabVIEW's 16-byte flattened EXT; exact, and big-endian by default.

        Raises InvalidEncodingError for the encodings the x87 rejects.

        >>> Ext80.from_float(0.1).to_flattened().hex()
        '3ffb999999999999a000000000000000'
        """
        order = check_order(byteorder)
        return _flat.to_flat(int(self.negative), self.exponent, self.mantissa).to_bytes(16, order)

    @property
    def kind(self) -> ExtKind:
        """The class of this encoding.

        >>> Ext80.from_float(float("inf")).kind.value
        'infinity'
        """
        return classify(self.exponent, self.mantissa)

    def canonical(self: _T) -> _T:
        """Return the canonical encoding: a pseudo-denormal becomes exponent 1.

        >>> Ext80(False, 0, 1 << 63).canonical().exponent
        1
        """
        if self.kind is ExtKind.PSEUDO_DENORMAL:
            return type(self)(self.negative, 1, self.mantissa)
        return self
