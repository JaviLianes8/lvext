"""Command line interface: ``lvext encode`` and ``lvext decode``."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import NoReturn

from . import __version__
from ._codec import double_bits
from ._errors import LvextError
from ._rounding import Rounding
from ._value import ByteOrder, Ext80, check_order, clean_hex

_NEGATIVE = re.compile(r"-(?:[0-9.]|inf|nan|snan)", re.IGNORECASE)

_EPILOG = """\
examples:
  lvext encode 1                         -> 3fff8000000000000000
  lvext encode -2.5                      -> c000a000000000000000
  lvext encode 1/3 --rounding toward-zero
  lvext encode 1 --byteorder little      -> 0000000000000080ff3f
  lvext encode 1 --width 16              -> 0000000000003fff8000000000000000
  lvext encode -1/3                      -> bffdaaaaaaaaaaaaaaab
  lvext encode -inf                      -> ffff8000000000000000
  lvext decode 3ffd8000000000000000      -> exact 0.25, float 0.25
  lvext decode "4000 c90f daa2 2168 c235" --json

VALUE is a decimal (2.5, 1e-4000), a fraction (1/3), inf, nan, snan or -0.
HEX is 20 hex digits, or 32 for a 16-byte container whose 6 most significant
bytes are padding; whitespace, underscores and a 0x prefix are ignored.
"""


class _Parser(argparse.ArgumentParser):
    """An ArgumentParser that reports usage errors with exit status 1."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def _parse_value(text: str) -> Decimal | Fraction:
    cleaned = text.strip()
    try:
        return Fraction(cleaned) if "/" in cleaned else Decimal(cleaned)
    except (InvalidOperation, ValueError, ZeroDivisionError):
        raise LvextError(f"not a number, or beyond the decimal range: {text!r}") from None


def _parse_hex(text: str, byteorder: ByteOrder) -> Ext80:
    cleaned = clean_hex(text)
    if len(cleaned) == 32:
        try:
            bits = int.from_bytes(bytes.fromhex(cleaned), byteorder)
        except ValueError:
            raise LvextError(f"not a hex string: {text!r}") from None
        return Ext80.from_int(bits & ((1 << 80) - 1))
    if len(cleaned) != 20:
        raise LvextError(f"expected 20 or 32 hex digits, got {len(cleaned)}")
    return Ext80.from_hex(cleaned, byteorder)


def _encode(args: argparse.Namespace) -> str:
    order = check_order(args.byteorder)
    value = Ext80.from_number(_parse_value(args.value), args.rounding)
    return value.to_int().to_bytes(args.width, order).hex()


def _decode(args: argparse.Namespace) -> str:
    value = _parse_hex(args.hex, check_order(args.byteorder))
    kind = value.kind
    exact = str(value.to_decimal()) if kind.is_valid else None
    narrowed = value.narrow(args.rounding)
    report = {
        "kind": kind.value,
        "sign": "-" if value.negative else "+",
        "exponent": f"{value.exponent:#06x}",
        "mantissa": f"{value.mantissa:#018x}",
        "exact": exact,
        "float": _float_text(narrowed.value),
        "float_hex": f"{double_bits(narrowed.value):016x}",
        "float_exact": narrowed.exact,
    }
    if args.json:
        return json.dumps(report)
    lines = [f"{key}: {_text(item)}" for key, item in report.items()]
    return "\n".join(lines)


def _float_text(value: float) -> str:
    if math.isnan(value):
        return "-nan" if math.copysign(1.0, value) < 0 else "nan"
    return repr(value)


def _text(item: object) -> str:
    if item is None:
        return "none (rejected by the 80387 and later)"
    if isinstance(item, bool):
        return "yes" if item else "no"
    return str(item)


def _add_byteorder(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--byteorder", choices=["big", "little"], default="big", help="byte order (default big)"
    )


def _build_parser() -> _Parser:
    parser = _Parser(
        prog="lvext",
        description="Encode and decode x87 80-bit extended-precision floats exactly.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"lvext {__version__}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    modes = [mode.value for mode in Rounding]
    enc = commands.add_parser("encode", help="number to 80-bit hex", epilog=_EPILOG)
    enc.formatter_class = argparse.RawDescriptionHelpFormatter
    enc.add_argument("value", metavar="VALUE", help="decimal, fraction, inf, nan, snan or -0")
    _add_byteorder(enc)
    enc.add_argument("--width", type=int, choices=[10, 16], default=10, help="output bytes")
    enc.add_argument("--rounding", choices=modes, default=modes[0], help="to 64 mantissa bits")
    enc.set_defaults(run=_encode)
    dec = commands.add_parser("decode", help="80-bit hex to exact value and float", epilog=_EPILOG)
    dec.formatter_class = argparse.RawDescriptionHelpFormatter
    dec.add_argument("hex", metavar="HEX", help="20 hex digits (or 32 for a 16-byte container)")
    _add_byteorder(dec)
    dec.add_argument("--rounding", choices=modes, default=modes[0], help="to float64")
    dec.add_argument("--json", action="store_true", help="print one JSON object")
    dec.set_defaults(run=_decode)
    return parser


def _protect_negative_values(argv: list[str]) -> list[str]:
    """Move a negative VALUE such as -1e-9, -1/3 or -inf behind ``--`` for argparse."""
    if "encode" not in argv or "--" in argv:
        return argv
    start = argv.index("encode") + 1
    negatives = [arg for arg in argv[start:] if _NEGATIVE.match(arg)]
    others = [arg for arg in argv[start:] if not _NEGATIVE.match(arg)]
    return argv[:start] + others + (["--", *negatives] if negatives else [])


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line interface and return the exit status."""
    raw = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(_protect_negative_values(raw))
    try:
        output = args.run(args)
    except LvextError as exc:
        print(f"lvext: error: {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0
