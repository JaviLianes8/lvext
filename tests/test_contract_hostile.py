"""Promises against hostile input: odd types, long numbers and broken output."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import time
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

import lvext
from lvext import Ext80, LvextError, unpack_ext, unpack_ext128
from lvext._cli import main

TIE = "1.0000000000000000000542101086242752217003726400434970855712890625"  # 1 + 2**-64


@pytest.mark.parametrize("data", [16, list(range(16)), "a" * 16, None, -1, 2**70, 10**13])
def test_unpack_ext128_refuses_other_types(data: Any) -> None:
    with pytest.raises(LvextError, match="data must be"):
        unpack_ext128(data)


@pytest.mark.parametrize(
    "reader",
    [
        Ext80.from_bytes,
        Ext80.from_flattened,
        unpack_ext,
        unpack_ext128,
    ],
)
def test_a_released_memoryview_is_an_lvext_error(reader: Any) -> None:
    view = memoryview(bytes(16))
    view.release()
    with pytest.raises(LvextError, match="cannot be read as bytes"):
        reader(view)


class _Lying(int):
    def __lt__(self, other: object) -> bool:
        return True

    def __le__(self, other: object) -> bool:
        return True

    def __eq__(self, other: object) -> bool:
        return True

    __hash__ = None  # type: ignore[assignment]


def test_int_subclass_fields_are_stored_as_plain_ints() -> None:
    with pytest.raises(LvextError, match="exponent must be an int in"):
        Ext80(False, _Lying(99999), 0)
    value = Ext80(False, _Lying(1), _Lying(5))
    assert type(value.exponent) is int and type(value.mantissa) is int
    assert value != Ext80(False, 2, 5)
    assert hash(value) == hash(Ext80(False, 1, 5))


@pytest.mark.parametrize(("tail", "mantissa"), [("0" * 20_000, 0), ("0" * 20_000 + "1", 1)])
def test_a_long_decimal_rounds_as_its_exact_value(tail: str, mantissa: int) -> None:
    value = Decimal(TIE + tail)
    assert Ext80.from_decimal(value) == Ext80.from_fraction(Fraction(value))
    assert Ext80.from_decimal(value).mantissa == (1 << 63) + mantissa
    assert Ext80.from_decimal(-value, "floor").mantissa == (1 << 63) + 1


def test_a_million_digits_are_read_quickly() -> None:
    start = time.perf_counter()
    Ext80.from_decimal(Decimal("0." + "7" * 1_000_000))
    assert time.perf_counter() - start < 2.0


def test_closed_output_is_one_error_line(monkeypatch: pytest.MonkeyPatch) -> None:
    closed, err = io.StringIO(), io.StringIO()
    closed.close()
    monkeypatch.setattr(sys, "stdout", closed)
    monkeypatch.setattr(sys, "stderr", err)
    assert main(["encode", "1"]) == 1
    assert err.getvalue() == "lvext: error: cannot write the output\n"


@pytest.mark.parametrize("args", [["encode", "1"], ["--version"], ["--help"], ["encode", "-h"]])
def test_a_reader_that_goes_away_gives_exit_1(args: list[str]) -> None:
    code = f"import os, sys; os.close(1); from lvext._cli import main; sys.exit(main({args!r}))"
    env = {**os.environ, "PYTHONPATH": str(Path(lvext.__file__).resolve().parents[1])}
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert result.returncode == 1
    assert result.stderr == "lvext: error: cannot write the output\n"


def test_usage_errors_are_one_bounded_line(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["decode", "00000000000000000000", "extra\nline", *["x" * 50] * 100])
    err = capsys.readouterr().err.splitlines()
    assert caught.value.code == 1
    assert err[-1].startswith("lvext: error: unrecognized arguments: extra line")
    assert len(err[-1]) <= 160 + len("lvext: error: ")
