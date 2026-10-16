"""Small argument checks shared by the codec, the value type and the command line.

``ByteOrder`` is the type of every ``byteorder`` argument: ``"big"`` or ``"little"``.

>>> Ext80.from_float(1.0).to_bytes("little") == Ext80.from_float(1.0).to_bytes()[::-1]
True
"""

from __future__ import annotations

from typing import Literal, cast

from ._errors import LvextError, require

ByteOrder = Literal["big", "little"]

_MAX_QUOTE = 40  # characters of a caller's value quoted in an error message


def short(value: object) -> str:
    """Return ``repr(value)``, cut to a bounded length for error messages."""
    if isinstance(value, int) and value.bit_length() > 128:
        return f"an int of {value.bit_length()} bits"
    try:
        text = repr(value)
    except Exception:  # a hostile __repr__ must not replace the real error
        return f"a {type(value).__name__} object"
    if len(text) <= _MAX_QUOTE:
        return text
    return f"{text[: _MAX_QUOTE - 3]}... ({len(text)} characters)"


def check_order(byteorder: object) -> ByteOrder:
    """Return the byte order unchanged, or raise LvextError if it is unknown."""
    if byteorder == "big":
        return "big"
    if byteorder == "little":
        return "little"
    raise LvextError(f"byteorder must be 'big' or 'little', got {short(byteorder)}")


def clean_hex(text: str) -> str:
    """Drop whitespace, underscores and a ``0x`` prefix from a hex string."""
    require(text, (str,), "hex text")
    cleaned = "".join(text.split()).replace("_", "")
    return cleaned[2:] if cleaned[:2].lower() == "0x" else cleaned


def as_bytes(data: object, what: str = "data") -> bytes:
    """Return the bytes of a bytes, bytearray or memoryview, or raise LvextError.

    A memoryview is read as its raw bytes, whatever its item format.
    """
    require(data, (bytes, bytearray, memoryview), what)
    try:
        return bytes(cast("bytes | bytearray | memoryview", data))
    except (TypeError, ValueError) as exc:  # a released memoryview, a hostile subclass
        raise LvextError(f"{what} cannot be read as bytes: {short(str(exc))}") from None


def parse_hex(text: str, digits: int) -> bytes:
    """Return the bytes of a hex string that must hold exactly ``digits`` hex digits."""
    cleaned = clean_hex(text)
    if len(cleaned) != digits:
        raise LvextError(f"expected {digits} hex digits, got {len(cleaned)}")
    try:
        return bytes.fromhex(cleaned)
    except ValueError:
        raise LvextError(f"not a hex string: {short(text)}") from None
