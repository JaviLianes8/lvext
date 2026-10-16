"""Contracts from the blind mutation round: each one kills a mutant that survived it."""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

import lvext
from lvext import (
    Ext80,
    InvalidEncodingError,
    LvextError,
    NotFiniteError,
    unpack_ext128,
)
from lvext._cli import main

_INT = 1 << 63
_QUIET = 1 << 62


def _decode_json(capsys: pytest.CaptureFixture[str], *args: str) -> dict[str, object]:
    assert main(["decode", *args, "--json"]) == 0
    report: dict[str, object] = json.loads(capsys.readouterr().out)
    return report


def test_hex_honours_byteorder() -> None:
    assert Ext80.from_float(1.0).hex("little") == "0000000000000080ff3f"


def test_nan_losing_payload_bit_10_is_not_exact() -> None:
    narrowed = Ext80(False, 0x7FFF, _INT | _QUIET | (1 << 10)).narrow()
    assert math.isnan(narrowed.value)
    assert narrowed.exact is False


def test_signaling_nan_narrows_inexact_even_with_no_lost_bits() -> None:
    narrowed = Ext80.from_hex("7fff8000000000000800").narrow()
    assert math.isnan(narrowed.value)
    assert narrowed.exact is False


def test_not_finite_is_not_an_invalid_encoding() -> None:
    assert not issubclass(NotFiniteError, InvalidEncodingError)
    with pytest.raises(NotFiniteError) as caught:
        Ext80.from_float(math.inf).to_fraction()
    assert not isinstance(caught.value, InvalidEncodingError)


@pytest.mark.parametrize("size", [15, 17, 32])
def test_unpack_ext128_needs_exactly_16_bytes(size: int) -> None:
    with pytest.raises(LvextError):
        unpack_ext128(bytes(size))


def test_width_only_takes_10_or_16() -> None:
    with pytest.raises(SystemExit) as caught:
        main(["encode", "1", "--width", "12"])
    assert caught.value.code == 1


@pytest.mark.parametrize("order", ["LITTLE", "Little", "BIG"])
def test_byteorder_is_exact_lowercase(order: str) -> None:
    with pytest.raises(LvextError):
        Ext80.from_float(1.0).to_bytes(order)  # type: ignore[arg-type]


def test_uppercase_0x_prefix_is_accepted() -> None:
    assert Ext80.from_hex("0X3FFF8000000000000000").to_float() == 1.0


class _HostileRepr:
    def __repr__(self) -> str:
        raise RuntimeError("hostile repr")


def test_any_failing_repr_keeps_the_real_error() -> None:
    with pytest.raises(LvextError, match="byteorder"):
        Ext80.from_float(1.0).to_bytes(_HostileRepr())  # type: ignore[arg-type]


def test_rounding_with_a_failing_repr_is_an_lvext_error() -> None:
    with pytest.raises(LvextError, match="rounding"):
        Ext80.from_fraction(1, _HostileRepr())  # type: ignore[arg-type]


def test_from_number_rounds_a_decimal_in_the_given_mode(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert Ext80.from_number(Decimal("0.1"), "toward-zero").hex() == "3ffbcccccccccccccccc"
    assert main(["encode", "0.1", "--rounding", "toward-zero"]) == 0
    assert capsys.readouterr().out == "3ffbcccccccccccccccc\n"


def test_decode_padded_container_honours_byteorder(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _decode_json(capsys, "0000000000000080ff3f000000000000", "--byteorder", "little")
    assert report["exact"] == "1"
    assert report["mantissa"] == "0x8000000000000000"


def test_decode_reports_infinity_and_nan_as_exact_text(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _decode_json(capsys, "7fff8000000000000000")["exact"] == "Infinity"
    assert _decode_json(capsys, "ffffc000000000000000")["exact"] == "-NaN"


def test_decode_flattened_line_is_big_endian_whatever_the_input_order(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _decode_json(capsys, "0000000000000080ff3f", "--byteorder", "little")
    assert report["flattened"] == "3fff0000000000000000000000000000"


def test_version_matches_pyproject() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    if not pyproject.is_file():
        pytest.skip("no pyproject.toml next to the tests")
    found = re.search(r'^version = "([^"]+)"', pyproject.read_text(encoding="utf-8"), re.M)
    assert found is not None
    assert lvext.__version__ == found.group(1)


def test_python_m_lvext_returns_the_exit_status() -> None:
    env = dict(os.environ, PYTHONPATH=str(Path(lvext.__file__).resolve().parents[1]))
    bad = subprocess.run(
        [sys.executable, "-m", "lvext", "encode", "nope"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert bad.returncode == 1
    good = subprocess.run(
        [sys.executable, "-m", "lvext", "encode", "1"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert (good.returncode, good.stdout) == (0, "3fff8000000000000000\n")


@pytest.mark.parametrize("name", ["FLOOR", "Floor", " floor", "floor\n", "toward_zero"])
def test_rounding_names_are_exact(name: str) -> None:
    with pytest.raises(LvextError, match="rounding"):
        Ext80.from_fraction(1, name)  # type: ignore[arg-type]


class _LooksLikeFloor:
    def __str__(self) -> str:
        return "floor"


def test_rounding_is_not_taken_from_str_of_an_object() -> None:
    with pytest.raises(LvextError, match="rounding"):
        Ext80.from_fraction(1, _LooksLikeFloor())  # type: ignore[arg-type]


class _InterruptingHash:
    def __hash__(self) -> int:
        raise KeyboardInterrupt


def test_an_interrupt_inside_the_rounding_lookup_is_not_swallowed() -> None:
    with pytest.raises(KeyboardInterrupt):
        Ext80.from_fraction(1, _InterruptingHash())  # type: ignore[arg-type]
