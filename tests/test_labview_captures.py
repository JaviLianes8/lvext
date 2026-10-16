"""lvext against what LabVIEW 2026 itself wrote (tests/fixtures/labview2026).

scripts/capture_labview.py ran three shipped VIs with front-panel datalogging on, each
with an EXT control and an EXT indicator, and kept both flattened values per run:

- ``double``: LVfloatExt.vi, whose library call doubles the value it is handed;
- ``deg_to_rad`` and ``rad_to_deg``: the vi.lib angle conversions, computed in EXT, so
  their outputs use all 64 bits of the extended significand.

Inputs reach LabVIEW over COM as doubles (``double`` holds the bit pattern sent).
"""

from __future__ import annotations

import hashlib
import json
import struct
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from lvext import Ext80, InvalidEncodingError, Rounding

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "labview2026"
DOC: dict[str, Any] = json.loads((FIXTURES / "ext_records.json").read_text(encoding="utf-8"))
RECORDS: list[dict[str, str]] = DOC["records"]


def _double(text: str) -> float:
    return float(struct.unpack(">d", bytes.fromhex(text))[0])


def _flat(text: str) -> Ext80:
    return Ext80.from_flattened(bytes.fromhex(text))


def _pi() -> Fraction:
    """Pi to about 200 bits by Machin's formula in integer arithmetic."""
    unit = 1 << 260

    def arctan_inverse(n: int) -> int:
        total, term, k, sign = 0, unit // n, 1, 1
        while term:
            total += sign * (term // k)
            term //= n * n
            k += 2
            sign = -sign
        return total

    return Fraction(4 * (4 * arctan_inverse(5) - arctan_inverse(239)), unit)


def test_the_capture_covers_all_three_vis() -> None:
    counts = {vi: sum(r["vi"] == vi for r in RECORDS) for vi in ("double", "deg_to_rad")}
    assert DOC["labview"].startswith("26.") and counts == {"double": 171, "deg_to_rad": 115}
    assert len(RECORDS) == 401


@pytest.mark.parametrize("record", RECORDS, ids=lambda r: f"{r['vi']}-{r['double']}")
def test_a_double_flattens_exactly_as_labview_wrote_it(record: dict[str, str]) -> None:
    value = Ext80.from_float(_double(record["double"]))
    assert value.to_flattened().hex() == record["input"]
    assert _flat(record["input"]) == value


def test_labview_quiets_a_signaling_nan_as_lvext_does() -> None:
    record = next(r for r in RECORDS if r["double"] == "7ff0000000000001")
    assert record["input"] == "7fff8000000000001000000000000000"
    assert _flat(record["input"]).kind.value == "quiet-nan"


def test_doubling_in_the_library_call_is_exact() -> None:
    finite = [r for r in RECORDS if r["vi"] == "double" and _flat(r["input"]).kind.is_finite]
    checked = 0
    for record in finite:
        value = _flat(record["input"]).to_fraction()
        if value:
            assert _flat(record["output"]) == Ext80.from_fraction(2 * value)
            checked += 1
    assert checked == 159


def test_doubled_largest_double_is_beyond_the_double_range() -> None:
    record = next(r for r in RECORDS if r["double"] == "7fefffffffffffff")
    assert record["output"] == "43fffffffffffffff000000000000000"
    out = _flat(record["output"])
    assert out.to_fraction() == 2 * Fraction(_double("7fefffffffffffff"))
    assert out.narrow() == (float("inf"), False)


def test_labview_writes_bits_lvext_refuses_or_canonicalizes() -> None:
    """The library call doubles by adding 1 to the exponent field, so a zero comes back
    as an unnormal and an infinity or NaN wraps into a pseudo-denormal of the other sign.
    LabVIEW flattens the unnormal as if its integer bit were set (the smallest normal),
    and a pseudo-denormal by shifting all 64 mantissa bits under exponent 0. lvext refuses the first (it has no
    value) and writes the second with its value, under exponent 1.
    """
    zero = next(r for r in RECORDS if r["double"] == "0000000000000000")
    assert zero["output"] == "0001" + "00" * 14
    with pytest.raises(InvalidEncodingError):
        Ext80(False, 1, 0).to_flattened()
    inf = next(r for r in RECORDS if r["double"] == "7ff0000000000000")
    assert inf["output"] == "80008000000000000000000000000000"
    pseudo = Ext80(True, 0, 1 << 63)
    assert pseudo.to_flattened().hex() == "80010000000000000000000000000000"
    assert _flat(pseudo.to_flattened().hex()).to_fraction() == pseudo.to_fraction()


@pytest.mark.parametrize(("vi", "constant"), [("deg_to_rad", 1), ("rad_to_deg", -1)])
def test_angle_constants_are_pi_over_180_correctly_rounded(vi: str, constant: int) -> None:
    one = next(r for r in RECORDS if r["vi"] == vi and r["double"] == "3ff0000000000000")
    exact = (_pi() / 180) ** constant
    assert _flat(one["output"]) == Ext80.from_fraction(exact)


@pytest.mark.parametrize("vi", ["deg_to_rad", "rad_to_deg"])
def test_labview_multiplies_in_ext_and_rounds_as_lvext_does(vi: str) -> None:
    """Each output is the exact product rounded once to nearest-even, and the three
    other modes each disagree with LabVIEW on some record: the oracle discriminates."""
    records = [r for r in RECORDS if r["vi"] == vi]
    one = next(r for r in records if r["double"] == "3ff0000000000000")
    constant = _flat(one["output"]).to_fraction()
    misses = dict.fromkeys(Rounding, 0)
    for record in records:
        product = _flat(record["input"]).to_fraction() * constant
        for mode in Rounding:
            got = Ext80.from_fraction(product, mode).to_flattened().hex()
            misses[mode] += got != record["output"]
    assert misses[Rounding.NEAREST_EVEN] == 0
    assert all(misses[mode] > 40 for mode in Rounding if mode is not Rounding.NEAREST_EVEN)


def test_outputs_use_the_low_significand_bits() -> None:
    outputs = [_flat(r["output"]) for r in RECORDS if r["vi"] == "deg_to_rad"]
    assert sum(value.mantissa & 0x7FF != 0 for value in outputs) > 100


@pytest.mark.parametrize("name", sorted(DOC["samples_sha256"]))
def test_raw_datalog_samples_hold_the_recorded_fields(name: str) -> None:
    data = (FIXTURES / name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == DOC["samples_sha256"][name]
    vi = name.removesuffix("_sample.dat")
    record = [r for r in RECORDS if r["vi"] == vi][2]
    assert data[-32:].hex() == record["input"] + record["output"]
