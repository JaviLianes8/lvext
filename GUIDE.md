# lvext guide

Everything lvext promises, in one place. Every Python block and every `console`
transcript here runs as part of the test suite.

## The two layouts

**x87 extended (10 bytes).** One sign bit, a 15-bit exponent biased by 16383 and a
64-bit significand whose top bit is an explicit integer bit (Intel SDM Vol. 1, 4.2 and
8.2.2). A finite encoding with exponent `e` and significand `m` has the value
`m * 2**(max(e, 1) - 16383 - 63)`. In memory the x87 stores it little-endian; lvext
defaults to big-endian, the order the hex digits are usually written in.

**LabVIEW's flattened EXT (16 bytes).** One sign bit, the same 15-bit exponent and a
112-bit fraction whose leading bit is implicit: the IEEE 754 binary128 layout, written
big-endian. The 63 fraction bits of the x87 significand sit at the top of the 112, so
every valid 80-bit value widens exactly. Reading a 16-byte value with more than 64
significant bits rounds once.

```python
from lvext import Ext80

x = Ext80.from_hex("3ffb cccc cccc cccc cccd")  # 0.1 rounded to 64 bits
assert x.to_flattened().hex() == "3ffb999999999999999a000000000000"
assert Ext80.from_flattened(x.to_flattened()) == x
```

## Encoding classes

`Ext80.kind` is an `ExtKind`. Every one of the 2**80 bit patterns has exactly one.

| ExtKind | Exponent | Integer bit | Fraction | Value |
| --- | --- | --- | --- | --- |
| `ZERO` | 0 | 0 | 0 | signed zero |
| `SUBNORMAL` | 0 | 0 | not 0 | below 2**-16382 |
| `PSEUDO_DENORMAL` | 0 | 1 | any | value of exponent 1; `canonical()` rewrites it |
| `NORMAL` | 1 to 32766 | 1 | any | normal number |
| `UNNORMAL` | 1 to 32766 | 0 | any | none: rejected by the 80387 and later |
| `INFINITY` | 32767 | 1 | 0 | signed infinity |
| `QUIET_NAN`, `SIGNALING_NAN` | 32767 | 1 | not 0 | NaN; bit 62 set means quiet |
| `PSEUDO_INFINITY`, `PSEUDO_NAN` | 32767 | 0 | 0 / not 0 | none: rejected |

`kind.is_valid` is false for the three rejected classes, `kind.is_finite` is true for
zero, subnormal, pseudo-denormal and normal, and `kind.is_nan` for the two NaNs.

## The public API

| Name | What it is |
| --- | --- |
| `Ext80(negative, exponent, mantissa)` | a frozen, hashable value holding the three fields; equality compares bits |
| `Ext80.from_int` / `to_int` | the 80-bit pattern as an integer, sign in bit 79 |
| `Ext80.from_bytes` / `to_bytes` | exactly 10 bytes, `byteorder="big"` or `"little"` |
| `Ext80.from_hex` / `hex` | 20 hex digits; spaces, underscores and `0x` are ignored on input |
| `Ext80.from_flattened` / `to_flattened` | LabVIEW's 16-byte flattened EXT |
| `Ext80.from_float` | a float, exactly; an int at its exact value, rounded to nearest-even beyond 64 significant bits |
| `Ext80.from_fraction`, `from_decimal`, `from_number` | exact numbers, rounded once |
| `to_fraction`, `to_decimal` | the exact value, never rounded |
| `narrow`, `to_float` | the nearest float, rounded once; `narrow` also says whether it is exact |
| `kind`, `canonical` | the encoding class; the canonical form of a pseudo-denormal |
| `ExtKind`, `Rounding`, `Narrowed` | the enums and the result of `narrow` |
| `ByteOrder`, `RoundingMode` | type aliases: `"big"` or `"little"`; a `Rounding` member or its name (documented here, as aliases carry no docstring) |
| `EXT80_MAX`, `EXT80_MIN_NORMAL`, `EXT80_MIN_SUBNORMAL`, `EXT80_EPSILON`, `EXT80_INDEFINITE` | named limits, as `Ext80` |
| `pack_ext`, `unpack_ext` | float to 10 bytes and back |
| `pack_ext128`, `unpack_ext128` | float to a zero-padded 16-byte container and back (not the flattened form) |
| `LvextError`, `InvalidEncodingError`, `NotFiniteError` | the errors, all `ValueError` |

Every argument named `rounding` takes a `Rounding` member or its string value
(`"nearest-even"`, `"floor"`, `"ceiling"`, `"toward-zero"`); every `byteorder` takes
`"big"` or `"little"`. Byte inputs may be `bytes`, `bytearray` or `memoryview`.

```python
from fractions import Fraction
from lvext import EXT80_EPSILON, EXT80_MAX, Ext80, Rounding

assert EXT80_EPSILON.to_fraction() == Fraction(1, 2**63)
assert EXT80_MAX.narrow() == (float("inf"), False)
assert Ext80.from_float(2**64 - 1).hex() == "403effffffffffffffff"
assert Ext80.from_fraction(Fraction(2, 3), "floor") == Ext80.from_fraction(
    Fraction(2, 3), Rounding.FLOOR
)
```

## Rounding

`from_fraction`, `from_decimal`, `from_number` (for non-floats) and `from_flattened`
round once to 64 significant bits; `narrow`, `to_float` and `unpack_ext` round once to
a double. The default is `Rounding.NEAREST_EVEN`; `FLOOR`, `CEILING` and `TOWARD_ZERO`
are the other x87 rounding-control modes. Underflow is gradual, a result that rounds to
zero keeps its sign, and overflow gives infinity or the largest finite value as IEEE
754 prescribes for the mode.

```python
from fractions import Fraction
from lvext import Ext80, Rounding

tiny = Fraction(1, 2**16500)
assert Ext80.from_fraction(tiny).hex() == "00000000000000000000"
assert Ext80.from_fraction(tiny, Rounding.CEILING).hex() == "00000000000000000001"
assert Ext80.from_fraction(-tiny).hex() == "80000000000000000000"
```

## Special values

- **From a float.** Signed zero and infinities map across. A NaN keeps its sign and
  payload; a signaling NaN comes out quiet, as the x87 `FLD` does.
- **To a float.** A NaN keeps its sign and the top 51 payload bits and comes out quiet.
  The rejected encodings give the x87 indefinite NaN (`EXT80_INDEFINITE`), as `FSTP`
  does with the invalid exception masked.
- **From a Decimal.** The payload of `NaN123` goes in the low 62 bits of the significand;
  `sNaN` without a payload becomes payload 1, because a signaling NaN needs a nonzero
  fraction. A payload of 2**62 or more raises `LvextError`.
- **To a Decimal.** Infinities and NaNs map back, payload included.
- **To the flattened form.** Every valid encoding widens exactly, NaN payload included;
  a pseudo-denormal is written with its value, under exponent 1. The rejected encodings
  raise `InvalidEncodingError`.
- **From the flattened form.** A NaN keeps its sign, its quiet bit and the top 62
  payload bits. A signaling NaN whose payload lies only in the 49 dropped bits gets
  payload 1, so it stays a signaling NaN.

```python
from decimal import Decimal
from lvext import Ext80

nan = Ext80.from_float(float("-nan"))
assert nan.kind.value == "quiet-nan" and nan.negative
assert str(Ext80.from_decimal(Decimal("sNaN")).to_decimal()) == "sNaN1"
```

## LabVIEW

- **In a library call.** LabVIEW's C headers (`cintools`) describe `floatExt` as two
  32-bit halves of the significand, low half first, then the 16-bit sign and exponent:
  the x87 layout, little-endian. Use `Ext80.from_bytes(data, "little")`.
- **Flattened.** LabVIEW 2026 writes the 16-byte binary128 layout, big-endian. The
  tests check 401 datalog records written by LabVIEW 2026 26.3.1f1 on Windows through
  three shipped VIs with EXT terminals (`tests/fixtures/labview2026`, made by
  `scripts/capture_labview.py`): every input double flattens exactly as LabVIEW wrote it,
  signed zeros, infinities, NaN payloads and the quieting of signaling NaNs included; a
  doubled `DBL_MAX` lands beyond the double range as expected; and the 230 products
  computed in EXT by the vi.lib angle conversions equal lvext's nearest-even rounding of
  the exact product, with constants that are pi/180 and 180/pi correctly rounded.
- **Where LabVIEW and lvext differ.** The capture VI's library call doubles a value by
  adding one to the exponent field, which turns zero into an unnormal and wraps an
  infinity or NaN into a pseudo-denormal. LabVIEW flattened the unnormal by dropping the
  integer bit (lvext raises `InvalidEncodingError`: the encoding has no value) and the
  pseudo-denormal by shifting all 64 significand bits under exponent 0, which halves its
  value (lvext writes the value, under exponent 1).
- **Not observed.** Values only reach LabVIEW over COM as doubles, so the captures hold
  no EXT below 2**-16382 and no NaN payload bits beyond a double's, and LabVIEW was not
  observed reading 16-byte values that carry more than 64 significant bits.
- **The 16-byte container.** `pack_ext128` and `unpack_ext128` zero-pad the 80-bit value
  at the top (with `"little"`, a 16-byte `long double` on x86-64 compilers such as GCC
  and Clang). That is not LabVIEW's flattened form: use `to_flattened` for LabVIEW.

## Command line

`lvext encode VALUE` prints the encoding of a decimal (`2.5`, `1e-4000`), a fraction
(`1/3`), `inf`, `nan`, `snan` or `-0`, rounded once with `--rounding` (default
`nearest-even`). `--byteorder little` reverses the bytes, `--width 16` prints the
zero-padded container and `--flattened` LabVIEW's flattened form; the last two cannot
be combined. A negative value needs no `--`.

`lvext decode HEX` reads 20 hex digits, or 32: LabVIEW's flattened form with
`--flattened` (rounded to 64 bits with `--rounding` if needed), otherwise the padded
container, whose six top bytes are ignored. It prints the class, sign, fields, the exact
value, the float (rounded with `--rounding`) and its bits, whether the float is exact,
and the flattened form; `--json` prints the same as one JSON object, with `null` where
a rejected encoding has no value. `python -m lvext` works the same way.

```console
$ lvext encode -1/3 --rounding toward-zero
bffdaaaaaaaaaaaaaaaa
$ lvext decode 3fff0000000000000000000000000000 --flattened --json
{"kind": "normal", "sign": "+", "exponent": "0x3fff", "mantissa": "0x8000000000000000", "exact": "1", "float": "1.0", "float_hex": "3ff0000000000000", "float_exact": true, "flattened": "3fff0000000000000000000000000000"}
```

Output goes to standard output with exit status 0. Bad input prints one
`lvext: error: ...` line to standard error and exits 1. A usage error (an unknown or
conflicting option) also exits 1, after the usage line, with argparse's own message
(`lvext encode: error: ...`), which quotes the option as given.

## Errors

| Error | Raised when |
| --- | --- |
| `LvextError` | an argument has the wrong type (a bool is never a number), length, byte order, rounding name, hex text or range; a Decimal NaN payload needs more than 62 bits |
| `InvalidEncodingError` | `to_fraction`, `to_decimal` or `to_flattened` on an unnormal, pseudo-infinity or pseudo-NaN |
| `NotFiniteError` | `to_fraction` on an infinity or NaN |

All three are `ValueError` subclasses, and the last two are `LvextError` subclasses.
Their messages quote at most 40 characters of the offending value.

## Upgrading from 0.2.0

- New: `Ext80.from_flattened` and `Ext80.to_flattened`, the command line's `--flattened`
  option and the `flattened` line of `decode`.
- `Ext80.from_float` (and so `pack_ext` and `pack_ext128`) takes an int at its exact
  value, rounding to nearest-even only beyond 64 significant bits; 0.2.0 converted it
  to a float first, so `2**64 - 1` became `2**64`, and an int beyond the float range
  raised `OverflowError`. Such an int now encodes like any other (`10**400` is in
  range), and one beyond the extended range gives infinity.
- An unknown rounding name raises `LvextError` for every value; 0.2.0 ignored it when
  the value was a zero, an infinity, a NaN or (in `from_number`) a float.
- Error messages quote at most 40 characters of the input.
- The `rounding` arguments are typed `RoundingMode` (exported): a member or its name.
- Public classes report `lvext` as their module, for example `lvext.InvalidEncodingError`
  in a traceback.
