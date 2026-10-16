"""The promise of from_flattened and to_flattened, LabVIEW's 16-byte EXT.

Expected patterns here are hand-derived from the binary128 layout (sign, 15-bit exponent
biased by 16383, 112-bit fraction); test_labview_captures.py checks the layout itself
against LabVIEW's own output.
"""

from __future__ import annotations

import random
from fractions import Fraction

import pytest

from lvext import (
    EXT80_MAX,
    EXT80_MIN_NORMAL,
    EXT80_MIN_SUBNORMAL,
    Ext80,
    ExtKind,
    InvalidEncodingError,
    LvextError,
    Rounding,
)

INT_BIT = 1 << 63
MODES = list(Rounding)


def flat(sign: int, exponent: int, fraction: int) -> bytes:
    return ((sign << 127) | (exponent << 112) | fraction).to_bytes(16, "big")


def flat_value(data: bytes) -> Fraction:
    """An independent binary128 decoder for finite patterns."""
    bits = int.from_bytes(data, "big")
    exponent, fraction = (bits >> 112) & 0x7FFF, bits & ((1 << 112) - 1)
    significand = fraction + (1 << 112 if exponent else 0)
    value = significand * Fraction(2) ** (max(exponent, 1) - 16383 - 112)
    return -value if bits >> 127 else value


GOLDEN = [
    (Ext80.from_float(1.0), "3fff" + "00" * 14),
    (Ext80.from_float(-2.5), "c0004" + "0" * 27),
    (Ext80.from_float(0.0), "00" * 16),
    (Ext80.from_float(-0.0), "80" + "00" * 15),
    (Ext80.from_float(float("inf")), "7fff" + "00" * 14),
    (Ext80.from_float(float("-inf")), "ffff" + "00" * 14),
    (Ext80(False, 0x7FFF, INT_BIT | 1 << 62), "7fff8" + "0" * 27),
    (Ext80(True, 0x7FFF, INT_BIT | 5), "ffff" + f"{5 << 49:028x}"),
    (EXT80_MAX, "7ffe" + "f" * 15 + "e" + "0" * 12),
    (EXT80_MIN_NORMAL, "0001" + "00" * 14),
    (EXT80_MIN_SUBNORMAL, "0000" + f"{1 << 49:028x}"),
    (Ext80(False, 0, (1 << 63) - 1), "0000" + f"{((1 << 63) - 1) << 49:028x}"),
]


@pytest.mark.parametrize(("value", "expected"), GOLDEN, ids=[g[1] for g in GOLDEN])
def test_golden_patterns_both_ways(value: Ext80, expected: str) -> None:
    assert value.to_flattened().hex() == expected
    assert value.to_flattened("little") == bytes.fromhex(expected)[::-1]
    for mode in MODES:
        assert Ext80.from_flattened(bytes.fromhex(expected), rounding=mode) == value
    assert Ext80.from_flattened(bytes.fromhex(expected)[::-1], "little") == value


def test_widening_is_exact_for_every_valid_encoding() -> None:
    rng = random.Random(128)
    for _ in range(4000):
        value = Ext80.from_int(rng.getrandbits(80))
        if not value.kind.is_valid:
            with pytest.raises(InvalidEncodingError):
                value.to_flattened()
            continue
        data = value.to_flattened()
        if value.kind.is_finite:
            assert flat_value(data) == value.to_fraction()
        for mode in MODES:
            assert Ext80.from_flattened(data, rounding=mode) == value.canonical()


def test_a_pseudo_denormal_is_written_with_its_value() -> None:
    pseudo = Ext80(False, 0, INT_BIT | 3)
    assert pseudo.kind is ExtKind.PSEUDO_DENORMAL
    assert pseudo.to_flattened() == pseudo.canonical().to_flattened() == flat(0, 1, 3 << 49)


@pytest.mark.parametrize("mantissa", [0, 1, INT_BIT >> 1])
@pytest.mark.parametrize("exponent", [1, 0x4000, 0x7FFF])
def test_rejected_encodings_have_no_flattened_form(exponent: int, mantissa: int) -> None:
    value = Ext80(False, exponent, mantissa)
    assert not value.kind.is_valid
    with pytest.raises(InvalidEncodingError, match="no flattened form"):
        value.to_flattened()


ONE = 0x3FFF
HALF_ULP = 1 << 48  # 2**-64 relative to 1: half a unit in the 64th bit


@pytest.mark.parametrize(
    ("fraction", "sign", "expected"),
    [
        (HALF_ULP, 0, {"nearest-even": 0, "floor": 0, "ceiling": 1, "toward-zero": 0}),
        (HALF_ULP, 1, {"nearest-even": 0, "floor": 1, "ceiling": 0, "toward-zero": 0}),
        (3 * HALF_ULP, 0, {"nearest-even": 2, "floor": 1, "ceiling": 2, "toward-zero": 1}),
        (HALF_ULP + 1, 0, {"nearest-even": 1, "floor": 0, "ceiling": 1, "toward-zero": 0}),
        (HALF_ULP - 1, 1, {"nearest-even": 0, "floor": 1, "ceiling": 0, "toward-zero": 0}),
    ],
)
def test_low_bits_round_once_in_each_mode(
    fraction: int, sign: int, expected: dict[str, int]
) -> None:
    for mode in MODES:
        got = Ext80.from_flattened(flat(sign, ONE, fraction), rounding=mode)
        assert (got.negative, got.exponent) == (bool(sign), ONE)
        assert got.mantissa == INT_BIT + expected[mode.value], mode


def test_rounding_up_carries_into_the_exponent() -> None:
    got = Ext80.from_flattened(flat(0, ONE, (1 << 112) - 1))
    assert got == Ext80.from_float(2.0)


def test_overflow_follows_ieee_for_each_mode() -> None:
    top = (1 << 112) - 1
    inf, big = Ext80.from_float(float("inf")), EXT80_MAX
    neg = Ext80(True, big.exponent, big.mantissa)
    expect = {"nearest-even": inf, "floor": big, "ceiling": inf, "toward-zero": big}
    for mode in MODES:
        assert Ext80.from_flattened(flat(0, 0x7FFE, top), rounding=mode) == expect[mode.value]
    assert Ext80.from_flattened(flat(1, 0x7FFE, top), rounding="ceiling") == neg


def test_tiny_values_underflow_gradually_and_keep_their_sign() -> None:
    assert Ext80.from_flattened(flat(1, 0, 1)) == Ext80.from_float(-0.0)
    assert Ext80.from_flattened(flat(0, 0, 1), rounding="ceiling") == EXT80_MIN_SUBNORMAL
    assert Ext80.from_flattened(flat(0, 0, 1 << 48)) == Ext80.from_float(0.0)
    assert Ext80.from_flattened(flat(0, 0, 3 << 48)) == Ext80(False, 0, 2)
    assert Ext80.from_flattened(flat(0, 0, (1 << 112) - 1)) == EXT80_MIN_NORMAL


def test_finite_rounding_matches_an_exact_oracle() -> None:
    rng = random.Random(16)
    for _ in range(3000):
        exponent = rng.choice([0, 1, rng.randrange(1, 0x7FFF), 0x7FFE, 0x3FFF])
        sign = rng.getrandbits(1)
        data = flat(sign, exponent, rng.getrandbits(rng.choice([1, 49, 112])))
        exact = flat_value(data)
        for mode in MODES:
            expected = Ext80.from_fraction(exact, mode) if exact else Ext80(sign == 1, 0, 0)
            assert Ext80.from_flattened(data, rounding=mode) == expected


def test_nan_keeps_sign_quiet_bit_and_top_payload() -> None:
    quiet = Ext80.from_flattened(flat(1, 0x7FFF, (1 << 111) | (0xABC << 60) | 0xFFFF))
    assert quiet == Ext80(True, 0x7FFF, INT_BIT | 1 << 62 | 0xABC << 11)
    signaling = Ext80.from_flattened(flat(0, 0x7FFF, 1 << 49))
    assert signaling == Ext80(False, 0x7FFF, INT_BIT | 1)
    low_only = Ext80.from_flattened(flat(0, 0x7FFF, (1 << 49) - 1))
    assert low_only == Ext80(False, 0x7FFF, INT_BIT | 1)
    assert low_only.kind is ExtKind.SIGNALING_NAN


@pytest.mark.parametrize("size", [0, 10, 15, 17])
def test_wrong_length_is_refused(size: int) -> None:
    with pytest.raises(LvextError, match=f"16 bytes, got {size}"):
        Ext80.from_flattened(bytes(size))


@pytest.mark.parametrize("data", ["3fff" + "00" * 14, [0] * 16, 7])
def test_wrong_type_is_refused(data: object) -> None:
    with pytest.raises(LvextError, match="data must be"):
        Ext80.from_flattened(data)  # type: ignore[arg-type]


def test_buffers_byte_order_and_rounding_names() -> None:
    raw = flat(0, ONE, HALF_ULP)
    assert Ext80.from_flattened(bytearray(raw)) == Ext80.from_flattened(memoryview(raw))
    assert Ext80.from_flattened(raw, rounding="ceiling").mantissa == INT_BIT + 1
    with pytest.raises(LvextError, match="byteorder"):
        Ext80.from_flattened(raw, "middle")  # type: ignore[arg-type]
    with pytest.raises(LvextError, match="byteorder"):
        Ext80.from_float(1.0).to_flattened("network")  # type: ignore[arg-type]
    with pytest.raises(LvextError, match="rounding"):
        Ext80.from_flattened(raw, rounding="up")  # type: ignore[arg-type]
