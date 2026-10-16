# lvext 1.0.0 certification report

Progress:
- [x] Branch `release/1.0.0` created from `main` (0.2.0, 5b98440)
- [x] Baseline gates run on 0.2.0
- [x] Real LabVIEW 2026 captures (item 7)
- [x] API review and 1.0.0 API changes (item 1)
- [x] Errors, typing, docstrings and doctests (items 2 to 5)
- [x] Contract, fuzz and author mutation round (items 6, 9, 18)
- [x] Docs: README, GUIDE, CHANGELOG (items 11, 12)
- [x] Packaging, e2e and upgrade from PyPI 0.2.0 (items 8, 10, 13, 14), author run
- [ ] Independent reviewer and five QA lenses report PASS (items 16, 19)
- [ ] Gates (item 15), final run
- [ ] PR and trace guard CLEAN (item 17); merge and publish left to the maintainer

## Baseline on 0.2.0 (before any change)

Fresh clone of `main` on the laptop, CPython 3.14.6:

| Command | Result |
| --- | --- |
| `ruff format --check .`, `ruff check .`, `mypy --strict src tests` | exit 0 |
| `pytest` | 293 passed |
| `pytest --doctest-modules src` | no doctests at all |

Defects found in 0.2.0:

- No support for LabVIEW's flattened EXT, although the library is aimed at LabVIEW users;
  the 16-byte helpers are a zero-padded container that silently reads LabVIEW's 16 bytes
  as a different number (LabVIEW's 1.0 reads as 0.0).
- `Ext80.from_float(2**64 - 1)` went through a float and gave `2**64`; an int beyond the
  float range raised `OverflowError` instead of an lvext error.
- An unknown rounding name was ignored for zeros, infinities, NaNs and floats.
- Error messages quoted the whole input (a 1 MB byte order string came back in full).

## Ground truth (item 7)

`tests/fixtures/labview2026/` holds what LabVIEW 2026 Community 26.3.1f1 wrote on this PC
on 2026-10-16. `scripts/capture_labview.py` drove three shipped VIs over LabVIEW's
ActiveX server with front-panel datalogging on; each has an EXT control and an EXT
indicator, and LabVIEW wrote both, flattened, to a datalog record per run:

- `LVfloatExt.vi` (examples, DLL Calling VIs): its library call doubles the value. 171
  runs: signed zeros, subnormal and extreme doubles, infinities, eight NaN bit patterns
  (quiet, signaling, with payloads, both signs) and 150 seeded random doubles.
- `Degrees to Radians (Scalar EXT).vi` and `Radians to Degrees (Scalar EXT).vi` (vi.lib):
  115 runs each, computed in EXT, so the outputs use all 64 significand bits.

`ext_records.json` keeps every pair (input bit pattern sent, both 16-byte fields) with
the LabVIEW version and date; three raw datalog files are kept with their SHA-256.
`tests/test_labview_captures.py` checks:

- every input double flattens exactly as LabVIEW wrote it (401 of 401), signaling NaNs
  quieted and payloads placed as lvext places them;
- the 159 nonzero finite doublings are exact, and `2 * DBL_MAX` lands beyond the double
  range;
- the angle constants are pi/180 and 180/pi correctly rounded to 64 bits, and all 230
  products equal lvext's nearest-even rounding of the exact product, while each of the
  other three modes disagrees on more than 40 of them;
- the two places where LabVIEW's bytes and lvext's differ, both from bit patterns the
  library call produced by adding one to the exponent field: an unnormal (LabVIEW drops
  the integer bit; lvext refuses it) and a pseudo-denormal (LabVIEW shifts the whole
  significand under exponent 0, halving it; lvext writes its value).

Not capturable over COM: EXT values below 2**-16382 and NaN payload bits beyond a
double's (inputs arrive as doubles: 64-bit integers and decimals sent as `VT_I8`,
`VT_UI8` and `VT_DECIMAL` were all converted to double first), and LabVIEW reading
16-byte values with more than 64 significant bits. The x87 FPU oracle of 0.2.0
(`tests/test_x87_hardware.py`, real `FLD`, `FSTP`, `FILD`, `FDIVP`) is kept as the
independent check of the 80-bit side, and the flattened reader is checked against an
exact binary128 decoder written in the test.

## API review (item 1)

Kept: all seventeen names of 0.2.0 with their signatures and defaults. Changed for 1.0.0
(all in CHANGELOG and the GUIDE upgrade section): `Ext80.from_flattened` and
`Ext80.to_flattened` added; `--flattened` and the `flattened` report line in the command
line; `from_float` takes ints exactly; unknown rounding names always refused; rounding
parameters typed as a member or its name; error messages bounded to 40 characters of
input; `Ext80` keeps its bit-level methods in a private base class (fields, methods and
equality unchanged); the public `dev` extra replaced by `requirements-dev.txt`.

## Author mutation round (item 18)

40 mutations over every module, each applied alone to a fresh clone of the pushed
branch, suite run with `-x` and no bytecode, file restored afterwards; baseline green
before and after.

| # | Module | Mutation | Caught by |
| --- | --- | --- | --- |
| 1 | `_flat` | flattened shift off by one | `test_cli::test_encode_flattened` |
| 2 | `_flat` | pseudo-denormal flattened under exponent 0 | `test_contract_flat::test_a_pseudo_denormal_is_written_with_its_value` |
| 3 | `_flat` | integer bit kept in the flattened fraction | `test_cli::test_encode_flattened` |
| 4 | `_flat` | low-only signaling NaN read as infinity | `test_contract_flat::test_nan_keeps_sign_quiet_bit_and_top_payload` |
| 5 | `_flat` | lowest dropped bit ignored on read | `test_cli::test_decode_flattened_rounds_to_64_bits` |
| 6 | `_flat` | subnormal read under exponent 1 | `test_contract_flat::test_golden_patterns_both_ways` |
| 7 | `_flat` | hidden bit added to subnormals | `test_contract_flat::test_tiny_values_underflow_gradually_and_keep_their_sign` |
| 8 | `_flat` | subnormal scale from exponent 0 | same |
| 9 | `_flat` | sign swapped for directed rounding | `test_cli::test_decode_flattened_rounds_to_64_bits` |
| 10 | `_flat` | rejected encodings flattened | `test_contract_flat::test_widening_is_exact_for_every_valid_encoding` |
| 11 | `_bits` | flattened length check loosened | `test_contract_flat::test_wrong_length_is_refused` |
| 12 | `_bits` | flattened read ignores byte order | `test_contract_api::test_error_messages_stay_short_for_huge_input` |
| 13 | `_bits` | flattened write ignores byte order | `test_cli::test_encode_flattened` |
| 14 | `_bits` | flattened read ignores the rounding mode | `test_cli::test_decode_flattened_rounds_to_64_bits` |
| 15 | `_value` | int goes through float | `test_contract_api::test_from_float_takes_an_int_at_its_exact_value` |
| 16 | `_value` | Decimal negative zero loses its sign | `test_cli::test_encode_special_values` |
| 17 | `_value` | `from_number` skips the rounding check | `test_contract_api::test_an_unknown_rounding_is_refused_whatever_the_value` |
| 18 | `_text` | messages quote 4000 characters | `test_contract_api::test_error_messages_stay_short_for_huge_input` |
| 19 | `_text` | huge int quoted by `repr` | survived; killed by `test_contract_api::test_an_int_out_of_range_is_described_by_its_size` |
| 20 | `_text` | `"little"` treated as `"big"` | `test_cli::test_encode_options` |
| 21 | `_text` | extra hex digits accepted | killed only by a timing test; now by `test_contract_api::test_hex_needs_exactly_its_digit_count` |
| 22 | `_rounding` | ties round away from even | `test_cli::test_decode_flattened_rounds_to_64_bits` |
| 23 | `_rounding` | floor overflow saturation inverted | `test_rounding::test_overflow_follows_ieee` |
| 24 | `_codec` | subnormal double exponent off by one | `test_contract::test_every_double_encodes_exactly_and_returns_unchanged` |
| 25 | `_codec` | narrowed NaN not quieted | `test_contract::test_special_values` |
| 26 | `_kind` | quiet and signaling swapped | `test_contract::test_special_values` |
| 27 | `_decimal` | `sNaN` without payload becomes infinity | `test_cli::test_encode_special_values` |
| 28 | `_decimal` | Decimal clamp far too early | `test_contract::test_finite_vectors_decode_encode_and_round_trip` |
| 29 | `_cli` | `encode --flattened` ignored | `test_cli::test_encode_flattened` |
| 30 | `_cli` | report's flattened form little-endian | `test_cli::test_decode_flattened_rounds_to_64_bits` |
| 31 | `_cli` | padded container drops the sign | survived; killed by `test_contract_api::test_cli_padded_container_keeps_the_sign` |
| 32 | `_cli` | negative value starting with a point needs `--` | survived; killed by `test_contract_api::test_cli_negative_value_may_start_with_a_point` |
| 33 | `_ext` | padding byte read into the value | `test_ext::test_padding_bytes_are_ignored_on_unpack` |
| 34 | `_bits` | exponent 32767 refused | collection error (the limits fail to build) |
| 35 | `_bits` | sign read from bit 78 | `test_cli::test_decode_json_report` |
| 36 | `_bits` | `canonical` leaves exponent 0 | `test_value::test_canonical_rewrites_a_pseudo_denormal` |
| 37 | `_rounding` | floor log2 off by one | `test_cli::test_encode_options` |
| 38 | `_codec` | subnormal result given a normal exponent | `test_contract::test_finite_vectors_decode_encode_and_round_trip` |
| 39 | `_codec` | NaN exactness inverted | `test_rounding::test_narrowing_nan_keeps_sign_and_payload` |
| 40 | `_cli` | negative NaN printed without its sign | `test_cli::test_decode_shows_the_sign_of_a_negative_nan` |

Result: 37 of 40 killed at once, 3 survivors (19, 31, 32) and one weak kill (21) closed
by contracts in 74a0328, each confirmed to fail on its mutant.

## Packaging and end-to-end (items 8, 10, 14), author run at ebaf6d6

- `python -m build` and `twine check --strict` on a clean clone.
- Wheel: the fourteen package modules, `py.typed`, LICENSE and metadata. Sdist: `src`,
  `tests` with the LabVIEW captures, `conftest.py`, README, GUIDE, CHANGELOG,
  CONTRIBUTING, LICENSE, pyproject and the `.gitignore` hatchling adds; no capture
  script, report or scratch files.
- The wheel in fresh venvs on CPython 3.10.19, 3.11.5, 3.12.12, 3.13.2, 3.14.2 and
  3.14.2 free-threaded, the suite run from the extracted sdist with `src` removed (so it
  imports the installed wheel and drives its console script): green on all six.
- Sabotage: with the installed console script removed, the end-to-end tests fail.
- PyPI 0.2.0 installed, then upgraded in place to the 1.0.0 wheel: `from_float(2**64-1)`
  `403f8000000000000000` then `403effffffffffffffff`; `from_float(10**400)`
  `OverflowError` then an encoding; `from_fraction(0, "up")` and `from_number(1.5, "up")`
  accepted then refused; `to_flattened` absent then present; a 100-character byte order
  quoted in full then cut; `decode` gains its `flattened` line.
