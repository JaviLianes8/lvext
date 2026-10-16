"""The argument parser of the ``lvext`` command."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from typing import NoReturn

from . import __version__
from ._rounding import Rounding

Handler = Callable[[argparse.Namespace], str]

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


def _add_byteorder(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--byteorder", choices=["big", "little"], default="big", help="byte order (default big)"
    )


def build_parser(encode: Handler, decode: Handler) -> _Parser:
    """Return the parser; each command stores its handler as ``run``."""
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
    enc.set_defaults(run=encode)
    dec = commands.add_parser("decode", help="80-bit hex to exact value and float", epilog=_EPILOG)
    dec.formatter_class = argparse.RawDescriptionHelpFormatter
    dec.add_argument("hex", metavar="HEX", help="20 hex digits (or 32 for a 16-byte container)")
    _add_byteorder(dec)
    dec.add_argument(
        "--rounding", choices=modes, default=modes[0], help="to float64 (and to 64 bits)"
    )
    dec.add_argument("--flattened", action="store_true", help="HEX is LabVIEW's flattened EXT")
    dec.add_argument("--json", action="store_true", help="print one JSON object")
    dec.set_defaults(run=decode)
    return parser


def protect_negative_values(argv: list[str]) -> list[str]:
    """Move a negative VALUE such as -1e-9, -1/3 or -inf behind ``--`` for argparse."""
    if "encode" not in argv or "--" in argv:
        return argv
    start = argv.index("encode") + 1
    negatives = [arg for arg in argv[start:] if _NEGATIVE.match(arg)]
    others = [arg for arg in argv[start:] if not _NEGATIVE.match(arg)]
    return argv[:start] + others + (["--", *negatives] if negatives else [])
