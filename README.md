# lvext

Exact pure-Python codec for x87 80-bit extended-precision floats.

## Install

```
pip install lvext
```

## Usage

```python
from decimal import Decimal
from fractions import Fraction

from lvext import Ext80, ExtKind, Rounding

# Every float fits exactly, and the bytes come out big-endian unless you ask.
one = Ext80.from_float(1.0)
assert one.hex() == "3fff8000000000000000"
assert one.to_bytes("little") == bytes.fromhex("0000000000000080ff3f")

# Decode to the exact value: a Fraction, or a Decimal with every digit.
value = Ext80.from_hex("4000 c90f daa2 2168 c235")
assert value.kind is ExtKind.NORMAL
assert str(value.to_decimal()).startswith("3.14159265358979323851280895940618620443")

# Narrow to a float; the result says whether anything was lost.
assert value.narrow() == (3.141592653589793, False)

# Build from exact numbers, rounding once, in any of the four x87 modes.
third = Ext80.from_fraction(Fraction(1, 3), Rounding.TOWARD_ZERO)
assert third.hex() == "3ffdaaaaaaaaaaaaaaaa"
assert Ext80.from_decimal(Decimal("0.1")).hex() == "3ffbcccccccccccccccd"
```

The float-in, float-out helpers from the first release are still there:

```python
from lvext import pack_ext, unpack_ext

assert pack_ext(-2.5) == bytes.fromhex("c000a000000000000000")
assert unpack_ext(pack_ext(-2.5)) == -2.5
```

## What it handles

- **The format.** 1 sign bit, a 15-bit exponent biased by 16383, an explicit integer
  bit and a 63-bit fraction (Intel SDM Vol. 1, 4.2 and 8.2.2). `Ext80` holds the
  three fields bit for bit, so all 2**80 encodings round-trip through bytes, hex and
  integers in either byte order. x87 memory order is little-endian.
- **Exact values.** `to_fraction()` and `to_decimal()` never round; the Decimal holds
  every digit (thousands of them near the ends of the range) whatever the context
  precision.
- **Rounding.** `from_fraction`, `from_decimal` and `from_number` round once to 64
  mantissa bits, and `narrow`/`to_float` round once to a double, with
  `Rounding.NEAREST_EVEN` (the default), `FLOOR`, `CEILING` or `TOWARD_ZERO`.
  Underflow is gradual; overflow gives infinity or the largest finite value as IEEE
  754 prescribes for the mode.
- **Special values.** Signed zero, infinities, quiet and signaling NaN with their
  payloads (a float carries the top 51 payload bits; a signaling NaN comes out quiet,
  as the FPU does). `Decimal("sNaN")` and `Decimal("NaN42")` map across both ways.
- **Legacy encodings.** `ExtKind` also names the encodings the 80387 and later
  reject: unnormal, pseudo-infinity and pseudo-NaN. They have no value, so
  `to_fraction()` raises `InvalidEncodingError` and `to_float()` returns the x87
  indefinite NaN, as the FPU does. A pseudo-denormal is accepted with the value of
  exponent 1; `canonical()` rewrites it.
- **Errors.** Every input error is an `LvextError`, which is a `ValueError`.
  `NotFiniteError` is raised when an infinity or NaN is asked for a Fraction.
- **Limits.** `EXT80_MAX`, `EXT80_MIN_NORMAL`, `EXT80_MIN_SUBNORMAL`, `EXT80_EPSILON`
  and `EXT80_INDEFINITE` are `Ext80` constants.

## Command line

```
$ lvext encode 1
3fff8000000000000000
$ lvext encode 1/3 --rounding toward-zero
3ffdaaaaaaaaaaaaaaaa
$ lvext encode -- -inf
ffff8000000000000000
$ lvext decode 3ffd8000000000000000
kind: normal
sign: +
exponent: 0x3ffd
mantissa: 0x8000000000000000
exact: 0.25
float: 0.25
float_hex: 3fd0000000000000
float_exact: yes
```

`encode` takes a decimal, a fraction such as `1/3`, `inf`, `nan`, `snan` or `-0`,
with `--byteorder`, `--rounding` and `--width 16` (zero-padded container).
`decode` takes 20 hex digits, or 32 for a 16-byte container, and `--json` prints one
JSON object. Errors go to stderr with exit status 1. `lvext --help` lists examples.

## How it is verified

Each golden vector in the contract tests is an exact rational written with
`fractions.Fraction`. On Windows x86-64 the test suite also runs the FPU's own load
and store instructions (`FLD`, `FSTP`, `FILD`, `FDIVP`) through a small test-only
`ctypes` helper and compares lvext with the hardware bit for bit, under all four
rounding modes, over the edge cases and thousands of random encodings. That check
found and now guards three decode bugs in 0.1.0 (see the changelog).

## LabVIEW

LabVIEW's EXT type is extended precision, but its flattened form is 16 bytes and NI
does not publish that layout in detail. lvext implements the x87 80-bit format only.
It does not decode the 16-byte flattened EXT, and none of its output has been
verified against LabVIEW. `pack_ext128` and `unpack_ext128` are a zero-padded
16-byte container (with `"little"`, the layout x86-64 compilers use for a 16-byte
`long double`), not a LabVIEW format.

## Why

The Python standard library cannot read this format: `struct` has no 80-bit code.
`numpy.longdouble` exposes it only where the platform's `long double` is the x87
type (for example Linux with GCC); on Windows with MSVC it is a 64-bit double. lvext
does the bit math in pure Python with no dependencies, so the same bytes decode the
same way on every platform, and exact conversions to Fraction and Decimal come with
it.

## License

MIT. See [LICENSE](LICENSE).

## Links

- Website: https://lianes8studio.com
- GitHub: https://github.com/JaviLianes8
- LinkedIn: https://www.linkedin.com/in/jlianes/
