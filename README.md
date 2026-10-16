# lvext

Exact pure-Python codec for x87 80-bit extended-precision floats and LabVIEW's
flattened EXT.

An x87 extended value is 10 bytes: a C `long double` on x86 Linux, and the layout of
LabVIEW's `floatExt`, the C type an EXT has when LabVIEW passes it to a library call on
Windows. When LabVIEW flattens an EXT (for example into a datalog file) it writes 16
bytes in the IEEE 754 binary128 layout instead. Python's `float` has 53 bits of
precision; both formats have 64. lvext reads and writes both layouts bit for bit,
converts them to and from exact `Fraction` and `Decimal` values, and rounds once, in
any of the four IEEE modes, wherever precision has to go.

## Install

```
pip install lvext
```

Python 3.10 or newer, no dependencies.

## Quick start

```python
from decimal import Decimal
from fractions import Fraction

from lvext import Ext80, ExtKind, Rounding

# Every float fits exactly. Bytes come out big-endian unless you ask.
one = Ext80.from_float(1.0)
assert one.hex() == "3fff8000000000000000"
assert one.to_bytes("little") == bytes.fromhex("0000000000000080ff3f")

# Decode to the exact value: a Fraction, or a Decimal with every digit.
value = Ext80.from_hex("4000 c90f daa2 2168 c235")
assert value.kind is ExtKind.NORMAL
assert str(value.to_decimal()).startswith("3.14159265358979323851280895940618620443")

# Narrow to a float; the result says whether anything was lost.
assert value.narrow() == (3.141592653589793, False)

# Build from exact numbers, rounding once, in any of the four modes.
third = Ext80.from_fraction(Fraction(1, 3), Rounding.TOWARD_ZERO)
assert third.hex() == "3ffdaaaaaaaaaaaaaaaa"
assert Ext80.from_decimal(Decimal("0.1")).hex() == "3ffbcccccccccccccccd"

# LabVIEW's flattened EXT: 16 bytes, big-endian.
flat = Ext80.from_float(0.1).to_flattened()
assert flat.hex() == "3ffb999999999999a000000000000000"
assert Ext80.from_flattened(flat).to_float() == 0.1
```

The float-in, float-out helpers of the first release are still there:

```python
from lvext import pack_ext, unpack_ext

assert pack_ext(-2.5) == bytes.fromhex("c000a000000000000000")
assert unpack_ext(pack_ext(-2.5)) == -2.5
```

## Command line

```console
$ lvext encode 1/3
3ffdaaaaaaaaaaaaaaab
$ lvext encode 0.1 --flattened
3ffb999999999999999a000000000000
$ lvext decode 3ffd8000000000000000
kind: normal
sign: +
exponent: 0x3ffd
mantissa: 0x8000000000000000
exact: 0.25
float: 0.25
float_hex: 3fd0000000000000
float_exact: yes
flattened: 3ffd0000000000000000000000000000
```

`lvext --help` lists every option; the [guide](https://github.com/JaviLianes8/lvext/blob/main/GUIDE.md#command-line)
describes them.

## How it is verified

- **The x87 FPU itself.** On Windows x86-64 the tests run the processor's own load and
  store instructions through a small test-only `ctypes` helper and compare lvext with
  the hardware bit for bit, in all four rounding modes, over edge cases and thousands
  of random encodings.
- **LabVIEW 2026.** 401 pairs of values that LabVIEW 2026 wrote itself, through three
  shipped VIs with EXT terminals: every double input flattens exactly as LabVIEW wrote
  it, and 230 products LabVIEW computed in EXT equal lvext's single rounding of the
  exact product (and differ from each of the other three modes). The guide lists the
  two corner cases where LabVIEW's bytes and lvext's differ, and why.
- **Exact arithmetic.** Golden vectors are exact rationals, rounding is checked against
  an exact oracle, and seeded fuzzing covers every reader and the command line.

## Why

- Python's `struct` has no 80-bit or 128-bit float format.
- `numpy.longdouble` is the x87 type only where the platform's C `long double` is (for
  example Linux on x86 with GCC); on Windows it is an 8-byte double.
- `numpy-quaddtype` adds a binary128 dtype to NumPy as a compiled extension; it needs
  NumPy and does not read the 80-bit layout.

lvext does the bit arithmetic in pure Python, so the same bytes decode the same way on
every platform, and it gives the exact value, not just the nearest float.

## Documentation

- [Guide](https://github.com/JaviLianes8/lvext/blob/main/GUIDE.md): the formats, every
  public name, rounding, special values, LabVIEW details, errors and upgrading from 0.2.
- [Changelog](https://github.com/JaviLianes8/lvext/blob/main/CHANGELOG.md)

## License

MIT. See [LICENSE](https://github.com/JaviLianes8/lvext/blob/main/LICENSE).

## Links

- Website: https://lianes8studio.com
- GitHub: https://github.com/JaviLianes8
- LinkedIn: https://www.linkedin.com/in/jlianes/
