import math

import pytest

from lvext import pack_ext, pack_ext128, unpack_ext, unpack_ext128

REPRESENTATIVE = [
    0.0,
    1.0,
    -1.0,
    0.5,
    -0.5,
    2.0,
    1234.5,
    3.141592653589793,
    1e300,
    1e-300,
    2.2250738585072014e-308,
]


@pytest.mark.parametrize("value", REPRESENTATIVE)
def test_round_trip_is_exact_for_doubles(value: float) -> None:
    assert unpack_ext(pack_ext(value)) == value


def test_round_trip_keeps_negative_zero() -> None:
    result = unpack_ext(pack_ext(-0.0))
    assert result == 0.0
    assert math.copysign(1.0, result) == -1.0


def test_round_trip_infinities() -> None:
    assert unpack_ext(pack_ext(math.inf)) == math.inf
    assert unpack_ext(pack_ext(-math.inf)) == -math.inf


def test_round_trip_nan() -> None:
    assert math.isnan(unpack_ext(pack_ext(math.nan)))


def test_round_trip_smallest_subnormal_double() -> None:
    tiny = 5e-324
    assert unpack_ext(pack_ext(tiny)) == tiny


def test_one_has_the_documented_byte_pattern() -> None:
    # sign 0, exponent 0x3fff (16383 = bias), integer bit set, fraction 0.
    assert pack_ext(1.0) == bytes.fromhex("3fff8000000000000000")


def test_two_has_the_documented_byte_pattern() -> None:
    # sign 0, exponent 0x4000 (16384), integer bit set, fraction 0.
    assert pack_ext(2.0) == bytes.fromhex("40008000000000000000")


def test_minus_one_sets_the_sign_bit() -> None:
    assert pack_ext(-1.0) == bytes.fromhex("bfff8000000000000000")


def test_big_and_little_endian_are_byte_reversed() -> None:
    big = pack_ext(1234.5, "big")
    little = pack_ext(1234.5, "little")
    assert little == big[::-1]
    assert unpack_ext(little, "little") == 1234.5


def test_padded_128_bit_round_trips() -> None:
    for value in (1.0, -2.0, 0.5, math.inf):
        assert unpack_ext128(pack_ext128(value)) == value


def test_padded_big_endian_puts_the_value_in_the_low_bytes() -> None:
    assert pack_ext128(1.0, "big") == bytes(6) + pack_ext(1.0, "big")


def test_padded_little_endian_puts_the_value_in_the_low_bytes() -> None:
    assert pack_ext128(1.0, "little") == pack_ext(1.0, "little") + bytes(6)


def test_padding_bytes_are_ignored_on_unpack() -> None:
    padded = bytes.fromhex("ffffffffffff") + pack_ext(2.0, "big")
    assert unpack_ext128(padded, "big") == 2.0


def test_normal_values_keep_the_explicit_integer_bit() -> None:
    mantissa = int.from_bytes(pack_ext(1234.5, "big"), "big") & ((1 << 64) - 1)
    assert mantissa & (1 << 63)


def test_unpack_rejects_wrong_length() -> None:
    with pytest.raises(ValueError):
        unpack_ext(b"\x00" * 9)


def test_unpack128_rejects_wrong_length() -> None:
    with pytest.raises(ValueError):
        unpack_ext128(b"\x00" * 10)


def test_unpack_rounds_once_in_the_subnormal_range() -> None:
    # Fixed in 0.2.0: 0.1.0 rounded to 53 bits and then again to the subnormal width.
    assert unpack_ext(bytes.fromhex("3bcc8000000000000001")) == 5e-324
    assert unpack_ext(bytes.fromhex("bbcc8000000000000001")) == -5e-324


def test_unpack_rejected_encodings_give_nan() -> None:
    # Fixed in 0.2.0: pseudo-infinity read as infinity and unnormals read as numbers.
    for text in ("7fff0000000000000000", "3fff7fffffffffffffff"):
        assert math.isnan(unpack_ext(bytes.fromhex(text)))


def test_unpack_keeps_the_nan_sign() -> None:
    assert math.copysign(1.0, unpack_ext(bytes.fromhex("ffffc000000000000000"))) == -1.0


def test_padded_rejects_unknown_byteorder() -> None:
    with pytest.raises(ValueError, match="byteorder"):
        pack_ext128(1.0, "middle")  # type: ignore[arg-type]
