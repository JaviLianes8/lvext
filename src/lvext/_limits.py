"""Named limits of the 80-bit extended format, as exact Ext80 values."""

from __future__ import annotations

from ._kind import EXP_MAX, INT_BIT, QUIET_BIT
from ._value import Ext80

EXT80_MAX = Ext80(False, EXP_MAX - 1, (1 << 64) - 1)
"""The largest finite value, (2 - 2**-63) * 2**16383."""

EXT80_MIN_NORMAL = Ext80(False, 1, INT_BIT)
"""The smallest positive normal value, 2**-16382."""

EXT80_MIN_SUBNORMAL = Ext80(False, 0, 1)
"""The smallest positive subnormal value, 2**-16445."""

EXT80_EPSILON = Ext80(False, 16383 - 63, INT_BIT)
"""The gap between 1 and the next larger value, 2**-63."""

EXT80_INDEFINITE = Ext80(True, EXP_MAX, INT_BIT | QUIET_BIT)
"""The x87 "real indefinite" quiet NaN, the default response to an invalid operation."""
