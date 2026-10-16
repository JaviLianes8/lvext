"""Seeded fuzzing: hostile and random input never crashes, hangs or blows up.

Every call either returns or raises LvextError; results obey the ordering of the
rounding modes; and the cost of the parsers grows linearly with the input.
"""

from __future__ import annotations

import contextlib
import io
import random
import time
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
from fractions import Fraction

import pytest

from lvext import Ext80, LvextError, Rounding, unpack_ext, unpack_ext128
from lvext._cli import main

SEED = 20261016
MODES = list(Rounding)


def _value(x: Ext80) -> Fraction | None:
    return x.to_fraction() if x.kind.is_finite else None


def test_random_bytes_in_every_reader() -> None:
    rng = random.Random(SEED)
    for _ in range(3000):
        ten, sixteen = rng.randbytes(10), rng.randbytes(16)
        order = rng.choice(["big", "little"])
        x = Ext80.from_bytes(ten, order)  # type: ignore[arg-type]
        assert x.to_bytes(order) == ten  # type: ignore[arg-type]
        assert isinstance(unpack_ext(ten), float) and isinstance(unpack_ext128(sixteen), float)
        got = [Ext80.from_flattened(sixteen, order, mode) for mode in MODES]  # type: ignore[arg-type]
        assert len({g.kind.is_nan for g in got}) == 1
        values = dict(zip(MODES, map(_value, got), strict=True))
        low, high = values[Rounding.FLOOR], values[Rounding.CEILING]
        if low is not None and high is not None:
            assert low <= high
            for mode in (Rounding.NEAREST_EVEN, Rounding.TOWARD_ZERO):
                middle = values[mode]
                assert middle is None or low <= middle <= high


def test_random_and_mutated_hex_text() -> None:
    rng = random.Random(SEED + 1)
    alphabet = "0123456789abcdefABCDEFxX_ -+.g" + chr(9) + chr(10) + chr(0xE9) + chr(0x660)
    for _ in range(4000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 40)))
        for reader in (Ext80.from_hex, lambda t: Ext80.from_flattened(bytes.fromhex(t))):
            with contextlib.suppress(LvextError, ValueError):
                reader(text)


def _cli(*args: str) -> int:
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        try:
            return main(list(args))
        except SystemExit as exc:
            return int(exc.code or 0)


def test_random_command_lines_exit_0_or_1() -> None:
    rng = random.Random(SEED + 2)
    pieces = ["1", "-2.5", "1/3", "-1/0", "1e-99999", "9e999999999", "nan", "snan", "-inf"]
    pieces += ["3fff8000000000000000", "3fff" + "0" * 28, "zz", "0x" + "f" * 20, "1/", "/2"]
    flags = ["--flattened", "--json", "--width", "16", "--byteorder", "little", "--rounding"]
    flags += ["floor", "--", "-x"]
    for _ in range(600):
        args = [rng.choice(["encode", "decode"])]
        args += [rng.choice(pieces + flags) for _ in range(rng.randrange(0, 5))]
        assert _cli(*args) in (0, 1), args


def test_random_numbers_round_consistently() -> None:
    rng = random.Random(SEED + 3)
    for _ in range(1500):
        exact = Fraction(rng.getrandbits(rng.randrange(1, 200)) + 1, 1 << rng.randrange(0, 300))
        exact *= rng.choice([1, -1])
        got = {mode: Ext80.from_fraction(exact, mode).to_fraction() for mode in MODES}
        assert got[Rounding.FLOOR] <= exact <= got[Rounding.CEILING]
        assert abs(got[Rounding.TOWARD_ZERO]) <= abs(exact)
        assert got[Rounding.NEAREST_EVEN] in (got[Rounding.FLOOR], got[Rounding.CEILING])
        text = f"{exact.numerator}/{exact.denominator}"
        assert Ext80.from_decimal(Decimal(exact.numerator) / Decimal(exact.denominator)).kind
        assert _cli("encode", text) == 0


def _seconds(call: Callable[[], object]) -> float:
    best = float("inf")
    for _ in range(3):
        start = time.perf_counter()
        with contextlib.suppress(LvextError):
            call()
        best = min(best, time.perf_counter() - start)
    return best


@pytest.mark.parametrize(
    "make",
    [
        lambda n: lambda: Ext80.from_hex(" " * n + "3fff8000000000000000"),
        lambda n: lambda: Ext80.from_hex("g" * n),
        lambda n: lambda: Ext80.from_flattened(bytes(16), "x" * n),
        lambda n: lambda: _cli("decode", "_" * n + "3fff8000000000000000"),
    ],
    ids=["spaces", "bad-hex", "bad-byteorder", "cli-separators"],
)
def test_text_cost_grows_linearly(make: Callable[[int], Callable[[], object]]) -> None:
    small, large = _seconds(make(20_000)), _seconds(make(320_000))
    assert large < max(small, 1e-4) * 16 * 4


@pytest.mark.parametrize(
    "make",
    [
        lambda n: lambda: Ext80.from_decimal(Decimal("1." + "3" * n)),
        lambda n: lambda: Ext80.from_fraction(Fraction(3**n, 7**n)),
        lambda n: lambda: _cli("encode", "1." + "7" * n),
    ],
    ids=["decimal-digits", "fraction-size", "cli-digits"],
)
def test_number_cost_stays_below_quadratic(make: Callable[[int], Callable[[], object]]) -> None:
    """Exact rounding of a long number is big-integer arithmetic: subquadratic, bounded."""
    small, large = _seconds(make(4_000)), _seconds(make(32_000))
    assert large < max(small, 1e-3) * 8 * 8 * 2
    assert large < 2.0


@pytest.mark.parametrize(
    "value",
    ["1e999999999999999999", "-1e-999999999999999999", "0e999999999", "1" * 100_000, "9" * 50],
    ids=["huge-exponent", "tiny-exponent", "zero", "many-digits", "fifty-nines"],
)
def test_extreme_decimals_are_fast(value: str) -> None:
    start = time.perf_counter()
    Ext80.from_decimal(Decimal(value))
    assert time.perf_counter() - start < 2.0
