import math
import struct
import sys
from fractions import Fraction

import pytest

from lvext import EXT80_MAX, EXT80_MIN_SUBNORMAL, Ext80, LvextError, Rounding

N, F, C, Z = (
    Rounding.NEAREST_EVEN,
    Rounding.FLOOR,
    Rounding.CEILING,
    Rounding.TOWARD_ZERO,
)
TWO = Fraction(2)


def _bits(value: float) -> str:
    return struct.pack(">d", value).hex()


@pytest.mark.parametrize(
    ("mode", "positive", "negative"),
    [
        (N, "3ffdaaaaaaaaaaaaaaab", "bffdaaaaaaaaaaaaaaab"),
        (F, "3ffdaaaaaaaaaaaaaaaa", "bffdaaaaaaaaaaaaaaab"),
        (C, "3ffdaaaaaaaaaaaaaaab", "bffdaaaaaaaaaaaaaaaa"),
        (Z, "3ffdaaaaaaaaaaaaaaaa", "bffdaaaaaaaaaaaaaaaa"),
    ],
)
def test_one_third_in_every_mode(mode: Rounding, positive: str, negative: str) -> None:
    assert Ext80.from_fraction(Fraction(1, 3), mode).hex() == positive
    assert Ext80.from_fraction(Fraction(-1, 3), mode).hex() == negative


def test_ties_go_to_even_at_64_bits() -> None:
    tie_down = 1 + TWO**-64  # halfway between 1 and 1 + 2**-63, last bit even
    tie_up = 1 + 3 * TWO**-64  # halfway between odd and even neighbours
    assert Ext80.from_fraction(tie_down).hex() == "3fff8000000000000000"
    assert Ext80.from_fraction(tie_up).hex() == "3fff8000000000000002"


def test_rounding_up_can_carry_into_the_exponent() -> None:
    just_below_two = 2 - TWO**-70
    assert Ext80.from_fraction(just_below_two).hex() == "40008000000000000000"
    assert Ext80.from_fraction(just_below_two, Z).hex() == "3fffffffffffffffffff"


@pytest.mark.parametrize(
    ("mode", "positive", "negative"),
    [
        (N, "7fff8000000000000000", "ffff8000000000000000"),
        (F, "7ffeffffffffffffffff", "ffff8000000000000000"),
        (C, "7fff8000000000000000", "fffeffffffffffffffff"),
        (Z, "7ffeffffffffffffffff", "fffeffffffffffffffff"),
    ],
)
def test_overflow_follows_ieee(mode: Rounding, positive: str, negative: str) -> None:
    huge = TWO**16384
    assert Ext80.from_fraction(huge, mode).hex() == positive
    assert Ext80.from_fraction(-huge, mode).hex() == negative


def test_largest_value_is_not_an_overflow() -> None:
    assert Ext80.from_fraction(EXT80_MAX.to_fraction()) == EXT80_MAX


@pytest.mark.parametrize(
    ("mode", "expected"),
    [(N, "00000000000000000000"), (F, "00000000000000000000"), (C, "00000000000000000001")],
)
def test_underflow_below_half_the_smallest_subnormal(mode: Rounding, expected: str) -> None:
    tiny = EXT80_MIN_SUBNORMAL.to_fraction() / 3
    assert Ext80.from_fraction(tiny, mode).hex() == expected


def test_gradual_underflow_keeps_subnormal_bits() -> None:
    value = Fraction(5) * TWO**-16445
    assert Ext80.from_fraction(value).hex() == "00000000000000000005"


def test_subnormal_rounding_up_becomes_the_smallest_normal() -> None:
    value = (TWO**63 - Fraction(1, 4)) * TWO**-16445
    assert Ext80.from_fraction(value).hex() == "00018000000000000000"


def test_zero_fraction_is_positive_zero() -> None:
    assert Ext80.from_fraction(0).hex() == "00000000000000000000"


def test_rounding_accepts_its_string_value() -> None:
    assert Ext80.from_fraction(Fraction(1, 3), "toward-zero").hex() == "3ffdaaaaaaaaaaaaaaaa"  # type: ignore[arg-type]


def test_unknown_rounding_is_an_lvext_error() -> None:
    with pytest.raises(LvextError, match="rounding"):
        Ext80.from_fraction(1, "up")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (N, "7ff0000000000000"),
        (F, "7fefffffffffffff"),
        (C, "7ff0000000000000"),
        (Z, "7fefffffffffffff"),
    ],
)
def test_narrowing_overflow_follows_ieee(mode: Rounding, expected: str) -> None:
    narrowed = EXT80_MAX.narrow(mode)
    assert _bits(narrowed.value) == expected
    assert narrowed.exact is False


def test_narrowing_rounds_once_in_the_subnormal_range() -> None:
    # 2**-1075 * (1 + 2**-63): double rounding would give zero, one rounding gives 5e-324.
    assert Ext80.from_hex("3bcc8000000000000001").to_float() == 5e-324


def test_narrowing_reports_exactness() -> None:
    assert Ext80.from_float(0.1).narrow() == (0.1, True)
    third = Ext80.from_fraction(Fraction(1, 3)).narrow()
    assert third.value == 1 / 3
    assert third.exact is False


def test_narrowing_largest_double_is_exact() -> None:
    assert Ext80.from_float(sys.float_info.max).narrow() == (sys.float_info.max, True)


def test_narrowing_nan_keeps_sign_and_payload() -> None:
    value = struct.unpack(">d", bytes.fromhex("fff8000000000123"))[0]
    narrowed = Ext80.from_float(value).narrow()
    assert _bits(narrowed.value) == "fff8000000000123"
    assert narrowed.exact is True


def test_narrowing_signaling_nan_quiets_it() -> None:
    narrowed = Ext80.from_hex("7fff8000000000000001").narrow()
    assert _bits(narrowed.value) == "7ff8000000000000"
    assert narrowed.exact is False


def test_narrowing_rejected_encodings_gives_the_indefinite_nan() -> None:
    for text in ("3fff7fffffffffffffff", "7fff0000000000000000", "7fff4000000000000000"):
        narrowed = Ext80.from_hex(text).narrow()
        assert math.isnan(narrowed.value)
        assert _bits(narrowed.value) == "fff8000000000000"
        assert narrowed.exact is False
