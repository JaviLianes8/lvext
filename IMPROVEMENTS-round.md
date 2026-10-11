# Improvements round: exact 80-bit extended values

This round turns lvext from a float-only packer into an exact codec for the x87
80-bit extended-precision format, fixes decode bugs found by checking the library
against the x87 FPU itself, and makes the documentation honest about what is and is
not verified for LabVIEW.

## Ground truth

The x87 extended format is fully specified (Intel SDM Vol. 1, section 4.2 and
section 8.2.2): 1 sign bit, a 15-bit exponent biased by 16383, an explicit integer
bit and a 63-bit fraction. Every vector in the test suite is checked two ways:

- exactly, with `fractions.Fraction` and `decimal.Decimal` (no floating point);
- against the hardware, on Windows x86-64, by a test-only helper that runs the FPU
  load and store instructions (`FLD`, `FSTP`, `FILD`, `FDIVP`) under each rounding
  control setting.

LabVIEW's flattened EXT is 16 bytes and NI does not publish its layout. No real
LabVIEW flatten of an EXT value could be captured for this project, so lvext makes no
claim about that layout. The previous README said LabVIEW flattens EXT as 10
big-endian bytes; that sentence is removed.

## Bugs found against the hardware (all fixed)

| Input (big-endian hex)   | x87 result (double) | lvext 0.1.0 result |
|--------------------------|---------------------|--------------------|
| `3bcc8000000000000001`   | `0000000000000001`  | `0000000000000000` |
| `7fff0000000000000000`   | NaN (indefinite)    | infinity           |
| `3fff7fffffffffffffff`   | NaN (indefinite)    | `1.0`              |

The first is double rounding: the 64-bit mantissa was rounded to 53 bits and then
rounded again when the result was subnormal. The other two are encodings that the
x87 rejects as invalid operands (pseudo-infinity and unnormal).

## Ranked improvements

1. **Exact value type.** A frozen `Ext80` holding sign, biased exponent and the
   64-bit mantissa, built from and written to bytes, hex and a raw integer, in
   either byte order. Nothing is rounded unless a conversion asks for it.
2. **Lossless Fraction and Decimal.** `to_fraction()` and `to_decimal()` return the
   exact value (a Decimal with every digit, never rounded by a context). The reverse,
   `from_fraction()`, `from_decimal()` and `from_number()`, round once, correctly.
3. **Rounding modes.** The four x87 rounding control modes (nearest-even, toward
   minus infinity, toward plus infinity, toward zero) for both directions: narrowing
   an exact value to 64 mantissa bits, and narrowing an Ext80 to a float64, with
   correct gradual underflow and IEEE overflow (infinity or the largest finite value).
4. **Every encoding classified.** `ExtKind` names zero, subnormal, normal, infinity,
   quiet NaN, signaling NaN and the legacy encodings the 80387 and later reject:
   pseudo-denormal (accepted, same value as exponent 1), unnormal, pseudo-infinity and
   pseudo-NaN. `canonical()` rewrites a pseudo-denormal into its normal form.
5. **Honest errors.** `LvextError` (a `ValueError`) with `InvalidEncodingError` for
   the rejected encodings and `NotFiniteError` when an infinity or NaN has no exact
   rational value. Narrowing an invalid encoding to float returns the x87 indefinite
   NaN, as the hardware does.
6. **NaN fidelity.** Sign and payload survive float to Ext80 and back (the payload is
   truncated to what a double can hold, as `FSTP` does). A signaling NaN is quieted on
   the way through, matching `FLD`. `Decimal('sNaN')` builds a signaling NaN.
7. **Typed narrowing result.** `narrow()` returns `Narrowed(value, exact)` so callers
   know whether the float lost information.
8. **Named limits.** `EXT80_MAX`, `EXT80_MIN_NORMAL`, `EXT80_MIN_SUBNORMAL`,
   `EXT80_EPSILON` and `EXT80_INDEFINITE` as `Ext80` constants.
9. **Command line.** `lvext encode` (decimal, fraction or special value to hex, with
   byte order, width and rounding options), `lvext decode` (hex to kind, exact decimal
   and nearest float, text or JSON), `--version`, examples in `--help`, errors on
   stderr with exit status 1.
10. **Legacy functions kept.** `pack_ext`, `unpack_ext`, `pack_ext128` and
    `unpack_ext128` keep their signatures and now run on the exact codec, which fixes
    the three bugs above. The 16-byte helpers are documented as a zero-padded
    container (the in-memory layout x86-64 compilers use for `long double`), not as a
    LabVIEW format.

## Out of scope

- Decoding LabVIEW's 16-byte flattened EXT: unverifiable without a real capture.
- Arithmetic on Ext80 values: this is a codec, not a soft-float library.
