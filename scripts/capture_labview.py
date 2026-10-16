"""Capture EXT ground truth from a local LabVIEW 2026 install (Windows only, needs pywin32).

LabVIEW is driven over its ActiveX server. Each shipped VI below has an EXT control and an
EXT indicator; the VI runs with front-panel datalogging on, and LabVIEW writes both values
to a datalog record in its flattened 16-byte form. Inputs arrive over COM as doubles.

- LVfloatExt.vi (examples, DLL Calling VIs): a library call doubles the value.
- Degrees to Radians (Scalar EXT).vi and Radians to Degrees (Scalar EXT).vi (vi.lib):
  computed in EXT, so the outputs carry all 64 bits of the extended significand.

    python scripts/capture_labview.py

Writes tests/fixtures/labview2026/ext_records.json and three raw datalog samples.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import random
import struct
import sys
import tempfile
from pathlib import Path
from typing import Any

import pythoncom  # type: ignore[import-not-found]
import win32com.client as client  # type: ignore[import-not-found]
import win32com.client.dynamic as dynamic  # type: ignore[import-not-found]

ROOT = r"C:\Program Files\National Instruments\LabVIEW 2026" + "\\"
VIS = {
    "double": ROOT + r"examples\Connectivity\Libraries and Executables\DLL Calling VIs"
    r"\LVfloatExt.vi",
    "deg_to_rad": ROOT + r"vi.lib\Utility\AngleManip\Degrees to Radians (Scalar EXT).vi",
    "rad_to_deg": ROOT + r"vi.lib\Utility\AngleManip\Radians to Degrees (Scalar EXT).vi",
}
OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "labview2026"


def bits(value: float) -> str:
    return struct.pack(">d", value).hex()


def double(text: str) -> float:
    return float(struct.unpack(">d", bytes.fromhex(text))[0])


def special_inputs() -> list[str]:
    named = [0.0, -0.0, 1.0, -2.5, 0.1, 1 / 3, 2.0**-1022, 5e-324, 2.0**-1022 - 5e-324]
    named += [sys.float_info.max, -sys.float_info.max, float("inf"), float("-inf")]
    raw = [bits(v) for v in named]
    # NaNs by bit pattern: quiet, negative, with payloads, and signaling ones.
    raw += ["7ff8000000000000", "fff8000000000000", "7ff8000000000001", "7ffc0000000000ff"]
    raw += ["fff123456789abcd", "7ff0000000000001", "7ff4000000000000", "fff7ffffffffffff"]
    return raw


def random_inputs(seed: int, count: int) -> list[str]:
    rng = random.Random(seed)
    out = []
    for _ in range(count):
        exp = rng.choice([rng.randrange(1, 2047), rng.randrange(1000, 1050), 0])
        frac = rng.getrandbits(52)
        out.append(f"{(rng.getrandbits(1) << 63) | (exp << 52) | frac:016x}")
    return out


def angle_inputs(seed: int, count: int) -> list[str]:
    rng = random.Random(seed)
    values = [1.0, 2.0, 30.0, 45.0, 60.0, 90.0, 180.0, 360.0, -720.0, 0.5, 1e-300, 1e300]
    values += [3.141592653589793, 6.283185307179586, 1.5707963267948966]
    values += [rng.uniform(-1000.0, 1000.0) for _ in range(count)]
    return [bits(v) for v in values]


def run(app: Any, path: str, inp: str, outp: str, raw: str, log: Path) -> bytes:
    vi = app.GetVIReference(path, "", False, 0)
    vi._FlagAsMethod("GetControlValue", "SetControlValue", "Run")
    if log.exists():
        log.unlink()
    vi.LogFilePath = str(log)
    vi.LogAtFinish = True
    try:
        vi.SetControlValue(inp, client.VARIANT(pythoncom.VT_R8, double(raw)))
        vi.Run(False)
    finally:
        vi.LogAtFinish = False
    return log.read_bytes()


def fields(data: bytes, names: tuple[str, str]) -> dict[str, str]:
    """Return the 16-byte hex of each named EXT field of the single record.

    Each field's type descriptor is the EXT code 0x0b and its label; the record holds the
    fields in descriptor order at the end of the file, 16 bytes each.
    """
    spots = sorted((data.index(b"@" + bytes([len(n)]) + n.encode()), n) for n in names)
    tail = data[len(data) - 16 * len(spots) :]
    return {name: tail[16 * i : 16 * i + 16].hex() for i, (_, name) in enumerate(spots)}


def main() -> int:
    app = dynamic.Dispatch("LabVIEW.Application")
    plan = [
        ("double", "input", "output", special_inputs() + random_inputs(26, 150)),
        ("deg_to_rad", "angle (deg)", "angle (rad)", angle_inputs(27, 100)),
        ("rad_to_deg", "angle (rad)", "angle (deg)", angle_inputs(28, 100)),
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    samples: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "record.dat"
        for vi, inp, outp, inputs in plan:
            for index, raw in enumerate(inputs):
                data = run(app, VIS[vi], inp, outp, raw, log)
                found = fields(data, (inp, outp))
                records.append(
                    {"vi": vi, "double": raw, "input": found[inp], "output": found[outp]}
                )
                if index == 2:
                    name = f"{vi}_sample.dat"
                    (OUT / name).write_bytes(data)
                    samples[name] = hashlib.sha256(data).hexdigest()
    doc = {
        "labview": str(app.Version),
        "date": datetime.date.today().isoformat(),
        "method": "front-panel datalog of shipped VIs driven over ActiveX; see the script",
        "vis": {key: value.replace(ROOT, "<LabVIEW 2026>\\") for key, value in VIS.items()},
        "samples_sha256": samples,
        "records": records,
    }
    text = json.dumps(doc, indent=1) + "\n"
    (OUT / "ext_records.json").write_text(text, encoding="utf-8", newline="\n")
    print(f"{len(records)} records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
