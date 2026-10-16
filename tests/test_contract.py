"""The complete promise of lvext, asserted over exact golden vectors.

Every expected value below is an exact rational written with Fraction, so the
vectors do not depend on floating point. The same encodings are also checked
against the x87 FPU in test_x87_hardware.py.
"""

import importlib.resources
import math
import struct
from fractions import Fraction

import pytest

import lvext
from lvext import (
    EXT80_EPSILON,
    EXT80_INDEFINITE,
    EXT80_MAX,
    EXT80_MIN_NORMAL,
    EXT80_MIN_SUBNORMAL,
    Ext80,
    ExtKind,
    InvalidEncodingError,
    NotFiniteError,
    pack_ext,
    unpack_ext,
)

PUBLIC_API: list[str] = [
    "EXT80_EPSILON",
    "EXT80_INDEFINITE",
    "EXT80_MAX",
    "EXT80_MIN_NORMAL",
    "EXT80_MIN_SUBNORMAL",
    "ByteOrder",
    "Ext80",
    "ExtKind",
    "InvalidEncodingError",
    "LvextError",
    "Narrowed",
    "NotFiniteError",
    "Rounding",
    "RoundingMode",
    "pack_ext",
    "pack_ext128",
    "unpack_ext",
    "unpack_ext128",
]

TWO = Fraction(2)

# (big-endian hex, kind, exact value)
FINITE = [
    ("3fff8000000000000000", ExtKind.NORMAL, Fraction(1)),
    ("bfff8000000000000000", ExtKind.NORMAL, Fraction(-1)),
    ("3ffd8000000000000000", ExtKind.NORMAL, Fraction(1, 4)),
    ("c000a000000000000000", ExtKind.NORMAL, Fraction(-5, 2)),
    ("40008000000000000000", ExtKind.NORMAL, Fraction(2)),
    ("7ffeffffffffffffffff", ExtKind.NORMAL, (2 - TWO**-63) * TWO**16383),
    ("00018000000000000000", ExtKind.NORMAL, TWO**-16382),
    ("00007fffffffffffffff", ExtKind.SUBNORMAL, (1 - TWO**-63) * TWO**-16382),
    ("00000000000000000001", ExtKind.SUBNORMAL, TWO**-16445),
    ("43fefffffffffffff800", ExtKind.NORMAL, (2 - TWO**-52) * TWO**1023),
    ("3bcd8000000000000000", ExtKind.NORMAL, TWO**-1074),
    ("3fc08000000000000000", ExtKind.NORMAL, TWO**-63),
]


@pytest.mark.parametrize(("text", "kind", "exact"), FINITE)
def test_finite_vectors_decode_encode_and_round_trip(
    text: str, kind: ExtKind, exact: Fraction
) -> None:
    value = Ext80.from_hex(text)
    assert value.kind is kind
    assert value.to_fraction() == exact
    assert Fraction(value.to_decimal()) == exact
    assert Ext80.from_fraction(exact) == value
    assert Ext80.from_decimal(value.to_decimal()) == value
    assert Ext80.from_bytes(value.to_bytes("little"), "little") == value
    assert value.to_bytes("little") == bytes.fromhex(text)[::-1]
    assert Ext80.from_int(int(text, 16)) == value
    assert value.hex() == text


@pytest.mark.parametrize("value", [1.0, 0.25, -2.5, 2.0, 5e-324, 1.7976931348623157e308])
def test_every_double_encodes_exactly_and_returns_unchanged(value: float) -> None:
    encoded = Ext80.from_float(value)
    assert encoded.to_fraction() == Fraction(value)
    assert encoded.narrow() == (value, True)
    assert unpack_ext(pack_ext(value)) == value


@pytest.mark.parametrize(
    ("text", "kind", "negative"),
    [
        ("00000000000000000000", ExtKind.ZERO, False),
        ("80000000000000000000", ExtKind.ZERO, True),
        ("7fff8000000000000000", ExtKind.INFINITY, False),
        ("ffff8000000000000000", ExtKind.INFINITY, True),
        ("7fffc000000000000000", ExtKind.QUIET_NAN, False),
        ("ffffc000000000000000", ExtKind.QUIET_NAN, True),
        ("7fff8000000000000001", ExtKind.SIGNALING_NAN, False),
    ],
)
def test_special_values(text: str, kind: ExtKind, negative: bool) -> None:
    value = Ext80.from_hex(text)
    assert value.kind is kind
    assert value.negative is negative
    narrowed = value.to_float()
    assert math.copysign(1.0, narrowed) == (-1.0 if negative else 1.0)
    if kind is ExtKind.ZERO:
        assert narrowed == 0.0
        assert value.to_fraction() == 0
    else:
        with pytest.raises(NotFiniteError):
            value.to_fraction()
        assert Ext80.from_decimal(value.to_decimal()) == value
    if kind is ExtKind.INFINITY:
        assert math.isinf(narrowed)
    if kind.is_nan:
        assert math.isnan(narrowed)


def test_float_specials_encode_to_the_x87_patterns() -> None:
    assert Ext80.from_float(math.inf).hex() == "7fff8000000000000000"
    assert Ext80.from_float(-math.inf).hex() == "ffff8000000000000000"
    assert Ext80.from_float(math.nan).hex() == "7fffc000000000000000"
    assert Ext80.from_float(-0.0).hex() == "80000000000000000000"
    signaling = struct.unpack(">d", bytes.fromhex("7ff0000000000001"))[0]
    assert Ext80.from_float(signaling).hex() == "7fffc000000000000800"


@pytest.mark.parametrize(
    "text", ["3fff7fffffffffffffff", "7fff0000000000000000", "7fff4000000000000000"]
)
def test_rejected_encodings_are_held_but_never_given_a_value(text: str) -> None:
    value = Ext80.from_hex(text)
    assert not value.kind.is_valid
    assert value.hex() == text
    with pytest.raises(InvalidEncodingError):
        value.to_fraction()
    assert struct.pack(">d", value.to_float()) == bytes.fromhex("fff8000000000000")


def test_pseudo_denormal_has_the_value_of_exponent_one() -> None:
    value = Ext80.from_hex("00008000000000000000")
    assert value.kind is ExtKind.PSEUDO_DENORMAL
    assert value.to_fraction() == TWO**-16382


def test_named_limits() -> None:
    assert EXT80_MAX.to_fraction() == (2 - TWO**-63) * TWO**16383
    assert EXT80_MIN_NORMAL.to_fraction() == TWO**-16382
    assert EXT80_MIN_SUBNORMAL.to_fraction() == TWO**-16445
    assert EXT80_EPSILON.to_fraction() == TWO**-63
    assert Ext80.from_fraction(1 + EXT80_EPSILON.to_fraction()).hex() == "3fff8000000000000001"
    assert EXT80_INDEFINITE.hex() == "ffffc000000000000000"
    assert EXT80_INDEFINITE.to_decimal().is_qnan()


def test_decimal_output_is_exact_not_rounded() -> None:
    third = Ext80.from_fraction(Fraction(1, 3))
    assert third.to_fraction() == Fraction(0xAAAAAAAAAAAAAAAB, 2**65)
    assert Fraction(third.to_decimal()) == third.to_fraction()
    assert third.to_decimal().as_tuple().exponent == -65


def test_all_lists_exactly_the_public_api() -> None:
    assert sorted(lvext.__all__) == sorted(PUBLIC_API)


def test_every_exported_name_resolves() -> None:
    for name in lvext.__all__:
        assert hasattr(lvext, name)


def test_version_is_a_three_part_string() -> None:
    parts = lvext.__version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)


def test_the_package_ships_type_information() -> None:
    assert importlib.resources.files("lvext").joinpath("py.typed").is_file()
