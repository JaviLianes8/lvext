"""Command line interface: ``lvext encode`` and ``lvext decode``."""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import sys
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from fractions import Fraction

from ._codec import double_bits
from ._errors import LvextError
from ._parser import build_parser, protect_negative_values
from ._text import ByteOrder, check_order, clean_hex, parse_hex, short
from ._value import Ext80


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


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line interface and return the exit status."""
    raw = list(sys.argv[1:] if argv is None else argv)
    try:
        parser = build_parser(_encode, _decode)
        args = parser.parse_args(protect_negative_values(raw))
    except SystemExit:
        if _flush_failed():  # --help or --version into a closed pipe
            return 1
        raise
    except (OSError, ValueError):
        if _flush_failed(force=True):
            return 1
        raise
    try:
        output = args.run(args)
    except LvextError as exc:
        print(f"lvext: error: {exc}", file=sys.stderr)
        return 1
    try:
        print(output, flush=True)
    except (OSError, ValueError, AttributeError):  # closed or broken output
        _flush_failed(force=True)
        return 1
    return 0


def _flush_failed(force: bool = False) -> bool:
    """Flush stdout; on failure report one error line and keep the exit quiet."""
    try:
        if force:
            raise OSError
        sys.stdout.flush()
    except (OSError, ValueError, AttributeError):
        _silence_stdout()
        print("lvext: error: cannot write the output", file=sys.stderr)
        return True
    return False


def _silence_stdout() -> None:
    """Point stdout at the null device so the interpreter's final flush stays quiet."""
    with contextlib.suppress(OSError):
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115
