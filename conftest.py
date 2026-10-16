"""Make the public names available to the doctests in every module."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

import pytest

import lvext


@pytest.fixture(autouse=True)
def _public_names(doctest_namespace: dict[str, object]) -> None:
    doctest_namespace.update({name: getattr(lvext, name) for name in lvext.__all__})
    doctest_namespace.update(Decimal=Decimal, Fraction=Fraction)
