"""Float-in, float-out helpers kept from the first release, now on the exact codec."""

from __future__ import annotations

from ._errors import LvextError
from ._value import ByteOrder, Bytes, Ext80, check_order

_LOW80 = (1 << 80) - 1


def pack_ext(value: float, byteorder: ByteOrder = "big") -> bytes:
    """Pack a float exactly into the 10-byte extended form (big-endian by default)."""
    return Ext80.from_float(value).to_bytes(byteorder)


def unpack_ext(data: Bytes, byteorder: ByteOrder = "big") -> float:
    """Unpack 10 bytes into the nearest float, rounding once as x87 FSTP does."""
    return Ext80.from_bytes(data, byteorder).to_float()


def pack_ext128(value: float, byteorder: ByteOrder = "big") -> bytes:
    """Pack a float into a 16-byte container: the 80-bit value zero-padded at the top.

    With ``"little"`` this is the in-memory layout x86-64 compilers use for a 16-byte
    ``long double``. It is not a documented LabVIEW flatten format.
    """
    return Ext80.from_float(value).to_int().to_bytes(16, check_order(byteorder))


def unpack_ext128(data: Bytes, byteorder: ByteOrder = "big") -> float:
    """Unpack a 16-byte container, ignoring the six padding bytes."""
    raw = bytes(data)
    if len(raw) != 16:
        raise LvextError(f"padded extended value must be 16 bytes, got {len(raw)}")
    return Ext80.from_int(int.from_bytes(raw, check_order(byteorder)) & _LOW80).to_float()
