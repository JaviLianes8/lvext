"""Exceptions raised by lvext. All of them are ValueError subclasses."""

from __future__ import annotations


class LvextError(ValueError):
    """Base class for every error lvext raises on bad input."""


class InvalidEncodingError(LvextError):
    """The bits are an encoding the 80387 and later reject as an invalid operand.

    These are the unnormal, pseudo-infinity and pseudo-NaN encodings. They carry no
    defined value, so an exact conversion refuses them.
    """


class NotFiniteError(LvextError):
    """An infinity or NaN was asked for an exact rational value it does not have."""


def require(value: object, kinds: tuple[type, ...], what: str) -> None:
    """Raise LvextError unless value is one of kinds; a bool never counts as a number."""
    if isinstance(value, bool) or not isinstance(value, kinds):
        names = " or ".join(kind.__name__ for kind in kinds)
        raise LvextError(f"{what} must be {names}, got {type(value).__name__}")
