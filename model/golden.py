"""Golden reference model.

C = A x B computed in int64, then masked to W bits, so it wraps mod 2^W exactly like the
hardware accumulator. The result is the raw W-bit pattern (unsigned), which is what the
testbench reads from the DUT. Use to_signed() to read it as a signed number.

This is the only copy of the reference model; tests import it from here.
"""

import numpy as np


def matmul_golden(A, B, W):
    """Return A x B masked to W bits, as an int64 array of unsigned W-bit values."""
    A = np.asarray(A, dtype=np.int64)
    B = np.asarray(B, dtype=np.int64)
    mask = (1 << W) - 1
    return (A @ B) & mask


def to_signed(x, W):
    """Read a W-bit unsigned pattern (int or int array) as a signed number."""
    x = np.asarray(x, dtype=np.int64)
    return np.where(x >= (1 << (W - 1)), x - (1 << W), x)
