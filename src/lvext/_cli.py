"""Command line interface: ``lvext encode`` and ``lvext decode``."""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
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
from ._text import ByteOrder, check_order, clean_hex, parse_hex, short
from ._value import Ext80

_NEGATIVE = re.compile(r"-(?:[0-9.]|inf|nan|snan)", re.IGNORECASE)

_EPILOG = """examples:
  lvext encode 1                         -> 3fff8000000000000000
  lvext encode -2.5                      -> c000a000000000000000
  lvext encode 1/3 --rounding toward-zero
  lvext encode 1 --byteorder little      -> 0000000000000080ff3f
  lvext encode 0.1 --flattened           -> 3ffb999999999999999a000000000000
  lvext encode 1 --width 16              -> 0000000000003fff8000000000000000
  lvext encode -inf                      -> ffff8000000000000000
  lvext decode 3ffd8000000000000000      -> exact 0.25, float 0.25
  lvext decode 3fff0000000000000000000000000000 --flattened
  lvext decode "4000 c90f daa2 2168 c235" --json

VALUE is a decimal (2.5, 1e-4000), a fraction (1/3), inf, nan, snan or -0.
HEX is 20 hex digits; 32 with --flattened for LabVIEW's flattened EXT (IEEE
binary128 layout), or 32 without it for a 16-byte container whose 6 most
significant bytes are padding. Whitespace, underscores and 0x are ignored.
"""


_MAX_USAGE_MESSAGE = 160


class _Parser(argparse.ArgumentParser):
    """An ArgumentParser that reports usage errors with exit status 1."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        flat = " ".join(message.split())  # one line, however the arguments looked
        if len(flat) > _MAX_USAGE_MESSAGE:
            flat = flat[: _MAX_USAGE_MESSAGE - 3] + "..."
        self.exit(1, f"{self.prog}: error: {flat}\n")


def _parse_value(text: str) -> Decimal | Fraction:
    cleaned = text.strip()
    try:
        return Fraction(cleaned) if "/" in cleaned else Decimal(cleaned)
    except (InvalidOperation, ValueError, ZeroDivisionError):
        raise LvextError(f"not a number, or too long or large to read: {short(text)}") from None


def _parse_hex(text: str, byteorder: ByteOrder, args: argparse.Namespace) -> Ext80:
    if args.flattened:
        return Ext80.from_flattened(parse_hex(text, 32), byteorder, args.rounding)
    digits = len(clean_hex(text))
    if digits == 32:
        bits = int.from_bytes(parse_hex(text, 32), byteorder)
        return Ext80.from_int(bits & ((1 << 80) - 1))
    if digits != 20:
        raise LvextError(f"expected 20 or 32 hex digits, got {digits}")
    return Ext80.from_hex(text, byteorder)


def _encode(args: argparse.Namespace) -> str:
    order = check_order(args.byteorder)
    value = Ext80.from_number(_parse_value(args.value), args.rounding)
    if args.flattened:
        return value.to_flattened(order).hex()
    return value.to_int().to_bytes(args.width or 10, order).hex()


def _decode(args: argparse.Namespace) -> str:
    value = _parse_hex(args.hex, check_order(args.byteorder), args)
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
        "flattened": value.to_flattened().hex() if kind.is_valid else None,
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
    layout = enc.add_mutually_exclusive_group()
    layout.add_argument("--width", type=int, choices=[10, 16], help="output bytes (default 10)")
    layout.add_argument("--flattened", action="store_true", help="LabVIEW's 16-byte flattened EXT")
    enc.add_argument("--rounding", choices=modes, default=modes[0], help="to 64 mantissa bits")
    enc.set_defaults(run=_encode)
    dec = commands.add_parser("decode", help="80-bit hex to exact value and float", epilog=_EPILOG)
    dec.formatter_class = argparse.RawDescriptionHelpFormatter
    dec.add_argument("hex", metavar="HEX", help="20 hex digits (or 32 for a 16-byte container)")
    _add_byteorder(dec)
    dec.add_argument(
        "--rounding", choices=modes, default=modes[0], help="to float64 (and to 64 bits)"
    )
    dec.add_argument("--flattened", action="store_true", help="HEX is LabVIEW's flattened EXT")
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
    try:
        print(output, flush=True)
    except (OSError, ValueError, AttributeError):  # closed or broken output
        _silence_stdout()
        print("lvext: error: cannot write the output", file=sys.stderr)
        return 1
    return 0


def _silence_stdout() -> None:
    """Point stdout at the null device so the interpreter's final flush stays quiet."""
    with contextlib.suppress(OSError):
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115
