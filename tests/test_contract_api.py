"""Promises added or tightened for 1.0.0: ints, argument checks and bounded messages."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from typing import Any

import pytest

from lvext import Ext80, LvextError, Rounding, pack_ext, pack_ext128, unpack_ext
from lvext._cli import main


def test_from_float_takes_an_int_at_its_exact_value() -> None:
    assert Ext80.from_float(2**64 - 1).hex() == "403effffffffffffffff"
    assert Ext80.from_float(-(2**63) - 1).hex() == "c03e8000000000000001"
    assert Ext80.from_float(2**64 + 1) == Ext80.from_float(2.0**64)
    assert Ext80.from_float(3 * 2**64 + 2) == Ext80.from_fraction(3 * 2**64 + 2)
    assert Ext80.from_float(1) == Ext80.from_float(1.0)
    assert Ext80.from_float(0) == Ext80.from_float(0.0)


def test_an_int_beyond_the_range_is_infinity_not_an_overflow_error() -> None:
    assert Ext80.from_float(10**5000).kind.value == "infinity"
    assert Ext80.from_float(-(10**5000)).negative
    assert pack_ext(10**5000) == bytes.fromhex("7fff8000000000000000")


def test_the_float_helpers_take_ints_exactly() -> None:
    assert pack_ext(2**64 - 1).hex() == "403effffffffffffffff"
    assert pack_ext128(2**63 + 1).hex() == "000000000000403e8000000000000001"
    assert unpack_ext(pack_ext(7)) == 7.0


@pytest.mark.parametrize("value", [True, False, "1", None, 1j])
def test_from_float_refuses_other_types(value: object) -> None:
    with pytest.raises(LvextError, match="value must be float or int"):
        Ext80.from_float(value)  # type: ignore[arg-type]


UP: Any = "up"


@pytest.mark.parametrize(
    "call",
    [
        lambda: Ext80.from_fraction(0, UP),
        lambda: Ext80.from_fraction(Fraction(1, 3), UP),
        lambda: Ext80.from_decimal(Decimal("0"), UP),
        lambda: Ext80.from_decimal(Decimal("NaN"), UP),
        lambda: Ext80.from_number(1.5, UP),
        lambda: Ext80.from_float(1.0).narrow(UP),
    ],
)
def test_an_unknown_rounding_is_refused_whatever_the_value(call: object) -> None:
    with pytest.raises(LvextError, match="rounding must be one of"):
        call()  # type: ignore[operator]


def test_rounding_members_and_names_are_interchangeable() -> None:
    third = Fraction(1, 3)
    for mode in Rounding:
        assert Ext80.from_fraction(third, mode) == Ext80.from_fraction(third, mode.value)


HUGE: Any = "z" * 1_000_000


@pytest.mark.parametrize(
    "call",
    [
        lambda: Ext80.from_hex("0x" + "g" * 18 + HUGE[:0]),
        lambda: Ext80.from_hex(HUGE),
        lambda: Ext80.from_float(1.0).to_bytes(HUGE),
        lambda: Ext80.from_fraction(1, HUGE),
        lambda: Ext80(False, 10**100000, 0),
        lambda: Ext80(False, 0, -(10**100000)),
        lambda: Ext80.from_flattened(b"\0" * 16, HUGE),
    ],
)
def test_error_messages_stay_short_for_huge_input(call: object) -> None:
    with pytest.raises(LvextError) as caught:
        call()  # type: ignore[operator]
    assert len(str(caught.value)) < 160


def test_bad_hex_quotes_the_text_briefly() -> None:
    with pytest.raises(LvextError, match=r"not a hex string: 'gg"):
        Ext80.from_hex("g" * 20)


def test_cli_messages_stay_short_for_huge_input(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["encode", "9" * 5000 + "x"]) == 1
    assert main(["decode", "f" * 5000]) == 1
    assert main(["decode", "g" * 32, "--flattened"]) == 1
    err = capsys.readouterr().err.splitlines()
    assert len(err) == 3 and all(len(line) < 120 for line in err)


def test_an_int_out_of_range_is_described_by_its_size() -> None:
    with pytest.raises(LvextError, match=r"got an int of 332193 bits"):
        Ext80(False, 10**100000, 0)


@pytest.mark.parametrize("digits", [19, 21, 22, 40])
def test_hex_needs_exactly_its_digit_count(digits: int) -> None:
    with pytest.raises(LvextError, match=f"expected 20 hex digits, got {digits}"):
        Ext80.from_hex("1" * digits)


def test_cli_padded_container_keeps_the_sign(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["decode", "ffffffffffff" + "bfff8000000000000000", "--json"]) == 0
    assert '"sign": "-"' in capsys.readouterr().out


def test_cli_negative_value_may_start_with_a_point(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["encode", "-.5e1"]) == 0
    assert capsys.readouterr().out == "c001a000000000000000\n"


def test_public_classes_name_the_package_as_their_module() -> None:
    import pickle

    import lvext

    for name in lvext.__all__:
        obj = getattr(lvext, name)
        if isinstance(obj, type):
            assert obj.__module__ == "lvext", name
    value = Ext80.from_float(-2.5)
    assert pickle.loads(pickle.dumps(value)) == value
    assert b"_value" not in pickle.dumps(value, protocol=0)
