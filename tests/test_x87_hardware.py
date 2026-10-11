"""lvext against the x87 FPU itself, bit for bit (Windows x86-64 only)."""

from __future__ import annotations

import random
import struct
from fractions import Fraction

import _x87
import pytest

from lvext import Ext80, Rounding

pytestmark = pytest.mark.skipif(not _x87.AVAILABLE, reason="needs Windows on x86-64")

MODES = list(Rounding)
_rng = random.Random(80)

SPECIAL_EXT = [
    "3fff8000000000000000",  # 1.0
    "3fff8000000000000400",  # 1 + 2**-53: a tie at double precision
    "3fff8000000000000c00",  # 1 + 3 * 2**-53: a tie that rounds up to even
    "7ffeffffffffffffffff",  # largest extended: overflows a double
    "43fefffffffffffffbff",  # just under the double overflow threshold
    "43fefffffffffffffc00",  # exactly at the double overflow threshold
    "3c00ffffffffffffffff",  # rounds up into the smallest normal double
    "3bcc8000000000000001",  # just above half the smallest subnormal double
    "3bcc8000000000000000",  # exactly half the smallest subnormal double
    "3bcd8000000000000000",  # the smallest subnormal double
    "00008000000000000000",  # pseudo-denormal
    "00000000000000000001",  # smallest extended subnormal
    "80000000000000000000",  # negative zero
    "7fff8000000000000000",  # infinity
    "7fffc000000000000000",  # quiet NaN
    "ffffc000000000000000",  # indefinite
    "7fff8000000000000001",  # signaling NaN
    "7fffffffffffffffffff",  # quiet NaN, full payload
    "3fff7fffffffffffffff",  # unnormal
    "7fff0000000000000000",  # pseudo-infinity
    "7fff4000000000000000",  # pseudo-NaN
]


def _lib_narrow(ext: bytes, mode: Rounding) -> bytes:
    return struct.pack(">d", Ext80.from_bytes(ext).to_float(mode))


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("ext_hex", SPECIAL_EXT)
def test_narrowing_edge_cases_match_fstp(ext_hex: str, mode: Rounding) -> None:
    ext = bytes.fromhex(ext_hex)
    assert _lib_narrow(ext, mode) == _x87.narrow(ext, mode.value)


@pytest.mark.parametrize("mode", MODES)
def test_narrowing_random_encodings_matches_fstp(mode: Rounding) -> None:
    for _ in range(3000):
        ext = _rng.getrandbits(80).to_bytes(10, "big")
        assert _lib_narrow(ext, mode) == _x87.narrow(ext, mode.value), ext.hex()


@pytest.mark.parametrize("mode", MODES)
def test_narrowing_random_near_double_range_matches_fstp(mode: Rounding) -> None:
    # Exponents around the double subnormal and overflow edges, both signs.
    for _ in range(3000):
        exponent = _rng.choice([_rng.randint(0x3BB0, 0x3C02), _rng.randint(0x43F0, 0x4400)])
        sign = _rng.getrandbits(1) << 15
        mantissa = _rng.getrandbits(64) | (1 << 63)
        ext = (sign | exponent).to_bytes(2, "big") + mantissa.to_bytes(8, "big")
        assert _lib_narrow(ext, mode) == _x87.narrow(ext, mode.value), ext.hex()


def test_widening_random_doubles_matches_fld() -> None:
    patterns = [_rng.getrandbits(64) for _ in range(3000)]
    patterns += [0x7FF0000000000001, 0xFFF0000000000001, 0x0000000000000001, 0x7FEFFFFFFFFFFFFF]
    for bits in patterns:
        double = bits.to_bytes(8, "big")
        value = struct.unpack(">d", double)[0]
        assert Ext80.from_float(value).to_bytes() == _x87.widen(double), double.hex()


@pytest.mark.parametrize("mode", MODES)
def test_rounding_a_quotient_matches_fdivp(mode: Rounding) -> None:
    pairs = [(1, 3), (-1, 3), (2, 3), (1, 10), (-7, 10), (2**63 - 1, 3), (-(2**63), 7)]
    pairs += [
        (_rng.randint(-(2**63), 2**63 - 1), _rng.choice([1, -1]) * _rng.randint(1, 2**63 - 1))
        for _ in range(2000)
    ]
    for num, den in pairs:
        if num == 0:
            continue
        expected = _x87.divide(num, den, mode.value)
        assert Ext80.from_fraction(Fraction(num, den), mode).to_bytes() == expected, (num, den)
