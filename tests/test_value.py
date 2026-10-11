from decimal import Decimal
from fractions import Fraction
from typing import Any

import pytest

from lvext import Ext80, ExtKind, LvextError

ONE = Ext80(False, 0x3FFF, 1 << 63)


def test_fields_are_validated() -> None:
    with pytest.raises(LvextError):
        Ext80(False, 0x8000, 0)
    with pytest.raises(LvextError):
        Ext80(False, 0, 1 << 64)
    with pytest.raises(LvextError):
        Ext80(False, -1, 0)
    with pytest.raises(LvextError):
        Ext80(1, 0, 0)  # type: ignore[arg-type]


def test_is_frozen_and_hashable() -> None:
    with pytest.raises(AttributeError):
        ONE.exponent = 1  # type: ignore[misc]
    assert {ONE, Ext80.from_float(1.0)} == {ONE}


def test_repr_shows_hex_fields() -> None:
    assert repr(ONE) == "Ext80(negative=False, exponent=0x3fff, mantissa=0x8000000000000000)"


def test_int_round_trip_puts_the_sign_in_bit_79() -> None:
    minus_one = Ext80.from_float(-1.0)
    assert minus_one.to_int() == 0xBFFF8000000000000000
    assert Ext80.from_int(minus_one.to_int()) == minus_one


def test_from_int_rejects_values_wider_than_80_bits() -> None:
    with pytest.raises(LvextError):
        Ext80.from_int(1 << 80)
    with pytest.raises(LvextError):
        Ext80.from_int(-1)


def test_bytes_in_both_orders() -> None:
    assert ONE.to_bytes() == bytes.fromhex("3fff8000000000000000")
    assert ONE.to_bytes("little") == bytes.fromhex("0000000000000080ff3f")
    assert Ext80.from_bytes(bytes.fromhex("0000000000000080ff3f"), "little") == ONE


def test_from_bytes_accepts_bytearray_and_memoryview() -> None:
    raw = bytes.fromhex("3fff8000000000000000")
    assert Ext80.from_bytes(bytearray(raw)) == ONE
    assert Ext80.from_bytes(memoryview(raw)) == ONE


def test_from_bytes_rejects_wrong_length() -> None:
    with pytest.raises(LvextError, match="10 bytes"):
        Ext80.from_bytes(b"\x00" * 16)


def test_unknown_byteorder_is_an_lvext_error() -> None:
    with pytest.raises(LvextError, match="byteorder"):
        ONE.to_bytes("middle")  # type: ignore[arg-type]


def test_hex_parsing_is_tolerant_of_separators() -> None:
    assert Ext80.from_hex("0x3fff_8000 0000 0000 0000") == ONE
    assert Ext80.from_hex("0000000000000080FF3F", "little") == ONE
    assert ONE.hex() == "3fff8000000000000000"


@pytest.mark.parametrize("text", ["3fff", "zzzz8000000000000000", "3fff80000000000000000000"])
def test_hex_parsing_rejects_bad_input(text: str) -> None:
    with pytest.raises(LvextError):
        Ext80.from_hex(text)


def test_from_number_dispatches_on_type() -> None:
    assert Ext80.from_number(1) == ONE
    assert Ext80.from_number(1.0) == ONE
    assert Ext80.from_number(Fraction(1)) == ONE
    assert Ext80.from_number(Decimal("1")) == ONE


def test_from_number_keeps_float_negative_zero() -> None:
    assert Ext80.from_number(-0.0).to_int() == 1 << 79


@pytest.mark.parametrize("value", [True, "1", None, 1j])
def test_from_number_rejects_other_types(value: object) -> None:
    with pytest.raises(LvextError):
        Ext80.from_number(value)  # type: ignore[arg-type]


def test_canonical_rewrites_a_pseudo_denormal() -> None:
    pseudo = Ext80(True, 0, 1 << 63)
    assert pseudo.kind is ExtKind.PSEUDO_DENORMAL
    assert pseudo.canonical() == Ext80(True, 1, 1 << 63)
    assert pseudo.canonical().to_fraction() == pseudo.to_fraction()
    assert ONE.canonical() is ONE


CLASSIFICATION = [
    ("00000000000000000000", ExtKind.ZERO),
    ("80000000000000000000", ExtKind.ZERO),
    ("00000000000000000001", ExtKind.SUBNORMAL),
    ("00008000000000000000", ExtKind.PSEUDO_DENORMAL),
    ("3fff8000000000000000", ExtKind.NORMAL),
    ("3fff7fffffffffffffff", ExtKind.UNNORMAL),
    ("00010000000000000000", ExtKind.UNNORMAL),
    ("7fff8000000000000000", ExtKind.INFINITY),
    ("7fff0000000000000000", ExtKind.PSEUDO_INFINITY),
    ("7fff4000000000000000", ExtKind.PSEUDO_NAN),
    ("7fffc000000000000000", ExtKind.QUIET_NAN),
    ("7fff8000000000000001", ExtKind.SIGNALING_NAN),
]


@pytest.mark.parametrize(("text", "kind"), CLASSIFICATION)
def test_every_encoding_class_is_named(text: str, kind: ExtKind) -> None:
    assert Ext80.from_hex(text).kind is kind


def test_kind_predicates() -> None:
    invalid = {ExtKind.UNNORMAL, ExtKind.PSEUDO_INFINITY, ExtKind.PSEUDO_NAN}
    finite = {ExtKind.ZERO, ExtKind.SUBNORMAL, ExtKind.NORMAL, ExtKind.PSEUDO_DENORMAL}
    for kind in ExtKind:
        assert kind.is_valid == (kind not in invalid)
        assert kind.is_finite == (kind in finite)
        assert kind.is_nan == (kind in {ExtKind.QUIET_NAN, ExtKind.SIGNALING_NAN})


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("from_float", ("1.5",)),
        ("from_float", (True,)),
        ("from_fraction", (True,)),
        ("from_fraction", (1.5,)),
        ("from_decimal", (1.5,)),
        ("from_int", (1.0,)),
        ("from_bytes", (10,)),
        ("from_hex", (b"3fff8000000000000000",)),
        ("__call__", (False, True, 0)),
        ("__call__", (False, 0, 1.0)),
    ],
)
def test_wrong_types_raise_lvext_error(name: str, args: tuple[object, ...]) -> None:
    build: Any = Ext80 if name == "__call__" else getattr(Ext80, name)
    with pytest.raises(LvextError, match="must be"):
        build(*args)


def test_hex_parsing_ignores_tabs_and_newlines() -> None:
    assert Ext80.from_hex("3fff\t8000 0000\n0000 0000") == ONE
