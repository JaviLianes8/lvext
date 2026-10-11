from decimal import Decimal, localcontext
from fractions import Fraction

import pytest

from lvext import (
    EXT80_MAX,
    EXT80_MIN_NORMAL,
    EXT80_MIN_SUBNORMAL,
    Ext80,
    InvalidEncodingError,
    LvextError,
    NotFiniteError,
    Rounding,
)


def test_decimal_is_exact_for_a_double() -> None:
    expected = Decimal("0.1000000000000000055511151231257827021181583404541015625")
    assert Ext80.from_float(0.1).to_decimal() == expected
    assert str(Ext80.from_float(0.1).to_decimal()) == str(expected)


def test_decimal_ignores_the_context_precision() -> None:
    with localcontext() as context:
        context.prec = 3
        digits = Ext80.from_float(0.1).to_decimal().as_tuple().digits
    assert len(digits) == 55


def test_decimal_of_integers_has_no_exponent() -> None:
    assert str(Ext80.from_float(1.0).to_decimal()) == "1"
    assert str(Ext80.from_float(-2.5).to_decimal()) == "-2.5"


def test_decimal_of_extreme_values_is_exact() -> None:
    for value in (EXT80_MAX, EXT80_MIN_NORMAL, EXT80_MIN_SUBNORMAL):
        assert Fraction(value.to_decimal()) == value.to_fraction()
    assert format(EXT80_MAX.to_decimal(), ".20e") == "1.18973149535723176502e+4932"
    assert format(EXT80_MIN_NORMAL.to_decimal(), ".20e") == "3.36210314311209350626e-4932"
    assert format(EXT80_MIN_SUBNORMAL.to_decimal(), ".20e") == "3.64519953188247460253e-4951"


def test_decimal_keeps_negative_zero() -> None:
    assert str(Ext80.from_float(-0.0).to_decimal()) == "-0"
    assert Ext80.from_decimal(Decimal("-0")).to_int() == 1 << 79


def test_decimal_specials_map_both_ways() -> None:
    cases = {
        "Infinity": "7fff8000000000000000",
        "-Infinity": "ffff8000000000000000",
        "NaN": "7fffc000000000000000",
        "-NaN": "ffffc000000000000000",
        "NaN42": "7fffc00000000000002a",
        "sNaN": "7fff8000000000000001",
        "sNaN7": "7fff8000000000000007",
    }
    for text, encoding in cases.items():
        built = Ext80.from_decimal(Decimal(text))
        assert built.hex() == encoding
        back = "sNaN1" if text == "sNaN" else text  # a signaling NaN needs a payload bit
        assert str(Ext80.from_hex(encoding).to_decimal()) == str(Decimal(back))


def test_nan_payload_too_large_is_an_error() -> None:
    with pytest.raises(LvextError, match="payload"):
        Ext80.from_decimal(Decimal("NaN" + str(2**62)))
    with pytest.raises(LvextError, match="payload"):
        Ext80.from_decimal(Decimal("NaN" + "9" * 5000))


def test_decimal_rounds_once_to_64_bits() -> None:
    assert Ext80.from_decimal(Decimal("0.1")).hex() == "3ffbcccccccccccccccd"
    assert Ext80.from_decimal(Decimal("0.1"), Rounding.FLOOR).hex() == "3ffbcccccccccccccccc"


def test_decimal_far_outside_the_range_is_fast_and_correct() -> None:
    assert Ext80.from_decimal(Decimal("1e999999999")).hex() == "7fff8000000000000000"
    assert Ext80.from_decimal(Decimal("-1e999999999"), Rounding.TOWARD_ZERO) == Ext80(
        True, 0x7FFE, (1 << 64) - 1
    )
    assert Ext80.from_decimal(Decimal("1e-999999999")).hex() == "00000000000000000000"
    tiny_up = Ext80.from_decimal(Decimal("1e-999999999"), Rounding.CEILING)
    assert tiny_up == EXT80_MIN_SUBNORMAL


def test_decimal_just_inside_the_range_is_not_clamped() -> None:
    value = Decimal("1.18973149535723176502e+4932")
    assert Ext80.from_decimal(value) == EXT80_MAX
    smallest = Decimal("3.6451995318824746025e-4951")
    assert Ext80.from_decimal(smallest) == EXT80_MIN_SUBNORMAL


def test_fraction_round_trip_is_lossless() -> None:
    value = Ext80.from_fraction(Fraction(22, 7))
    assert Ext80.from_fraction(value.to_fraction()) == value
    assert Ext80.from_decimal(value.to_decimal()) == value


def test_fraction_of_specials_raises_not_finite() -> None:
    for text in ("7fff8000000000000000", "7fffc000000000000000", "7fff8000000000000001"):
        with pytest.raises(NotFiniteError):
            Ext80.from_hex(text).to_fraction()


def test_rejected_encodings_raise_invalid_encoding() -> None:
    for text in ("3fff7fffffffffffffff", "7fff0000000000000000", "7fff4000000000000000"):
        value = Ext80.from_hex(text)
        with pytest.raises(InvalidEncodingError):
            value.to_fraction()
        with pytest.raises(InvalidEncodingError):
            value.to_decimal()


def test_errors_are_value_errors() -> None:
    assert issubclass(LvextError, ValueError)
    assert issubclass(InvalidEncodingError, LvextError)
    assert issubclass(NotFiniteError, LvextError)
