# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-10-16

The API below is now stable: names, signatures, defaults and error types will only
change in a new major version. Stable: `Ext80` and its methods, `ExtKind`, `Rounding`,
`Narrowed`, `ByteOrder`, the `EXT80_*` limits, `pack_ext`, `unpack_ext`, `pack_ext128`,
`unpack_ext128`, the three errors, and the `lvext` command with its output formats.

### Added

- `Ext80.from_flattened` and `Ext80.to_flattened` for LabVIEW's 16-byte flattened EXT
  (IEEE 754 binary128 layout, big-endian by default). Widening is exact; reading rounds
  once to 64 bits in the chosen mode. Checked against 401 datalog records written by
  LabVIEW 2026.
- `lvext encode --flattened`, `lvext decode --flattened`, and a `flattened` line (JSON
  key) in the `decode` report.
- The guide (GUIDE.md), runnable examples in every public docstring, and seeded fuzz
  tests.

### Changed

- `Ext80.from_float`, and so `pack_ext` and `pack_ext128`, take an int at its exact
  value, rounding to nearest-even only beyond 64 significant bits. 0.2.0 converted the
  int to a float first (`2**64 - 1` became `2**64`) and raised `OverflowError` for an
  int beyond the float range; such an int now encodes like any other, and one beyond
  the extended range gives infinity.
- An unknown rounding name raises `LvextError` whatever the value. 0.2.0 ignored it when
  the value was a zero, an infinity, a NaN or (in `from_number`) a float.
- Error messages quote at most 40 characters of the offending value; command line
  usage errors are one line of at most 160 characters.
- The `rounding` parameters are typed to accept the mode names (`"floor"` and so on)
  as well as the `Rounding` members, as they always did at run time.
- `Ext80` keeps its bit-level methods in a private base class; its fields, methods and
  equality are unchanged, except that `canonical()` on a subclass returns that subclass.
- `RoundingMode` is exported: the type of every `rounding` parameter.
- Public classes report `lvext` as their module (`lvext.Ext80` in reprs, tracebacks and
  new pickles); pickles made by 0.2.0 still load.
- `unpack_ext128` checks its argument's type like the other readers (0.2.0 read an int
  `n` as `n` zero bytes and a list as bytes), and a released memoryview raises
  `LvextError` instead of a plain `ValueError`.
- `Ext80` stores its exponent and mantissa as plain ints, so an int subclass cannot
  change comparisons, equality or hashing.
- A Decimal with very many digits is read in linear time: digits beyond 12,000 only
  decide rounding as "zero or not", so they are folded into one (results unchanged).
- The command line exits 1 with one error line when its output cannot be written,
  instead of a traceback.
- Package metadata: Production/Stable, supported Python versions listed, the `dev`
  extra replaced by `requirements-dev.txt`.


## [0.2.0]

### Added

- `Ext80`, an exact frozen value type for the x87 80-bit extended format: bytes, hex
  and integer conversion in either byte order; `from_float`, `from_fraction`,
  `from_decimal` and `from_number`; `to_fraction` and `to_decimal` with no rounding;
  `narrow` and `to_float`; `kind` and `canonical`.
- `Rounding` with the four x87 rounding modes, applied when rounding to 64 mantissa
  bits and when narrowing to a float, with gradual underflow and IEEE overflow.
- `ExtKind`, naming every encoding class, including pseudo-denormal, unnormal,
  pseudo-infinity and pseudo-NaN.
- `Narrowed`, the typed result of `narrow`: the float and whether it is exact.
- `LvextError`, `InvalidEncodingError` and `NotFiniteError`.
- `EXT80_MAX`, `EXT80_MIN_NORMAL`, `EXT80_MIN_SUBNORMAL`, `EXT80_EPSILON` and
  `EXT80_INDEFINITE`.
- The `lvext` command (`encode`, `decode`, `--version`), also runnable as
  `python -m lvext`.

### Fixed

- `unpack_ext` rounded twice for results in the double subnormal range, so
  `3bcc8000000000000001` gave `0.0` instead of `5e-324`. It now rounds once.
- `unpack_ext` read pseudo-infinity as infinity and unnormals as numbers. They now
  give the x87 indefinite NaN, matching the FPU.
- `unpack_ext` dropped the sign and payload of a NaN; both are now kept.

### Changed

- Length and byte order errors raise `LvextError`, still a `ValueError`.
- The documentation no longer states a LabVIEW flatten layout. The 16-byte helpers
  are described as a zero-padded container, not a documented LabVIEW format.
- Inputs of the wrong type (for example a string or a bool where a number is
  expected) raise `LvextError` instead of being coerced.

## [0.1.0]

- First release: `pack_ext`, `unpack_ext`, `pack_ext128` and `unpack_ext128` for
  the LabVIEW/x87 80-bit extended-precision float and its 128-bit padded storage
  form, with configurable byte order and full handling of signed zero,
  subnormals, infinities and NaN. (The LabVIEW attribution in this entry was never
  verified against LabVIEW output; see 0.2.0.)
