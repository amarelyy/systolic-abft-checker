"""ABFT checksum model for C = A x B (row and column checksums, mod 2^W).

Column checksums: the sum of each column of C must equal (column sums of A) x B.
Row checksums:    the sum of each row of C must equal A x (row sums of B).

Everything is computed modulo 2^W, like the hardware accumulator. Checksums are linear, so the
identity still holds when individual results wrap around. The output C is the raw W-bit
pattern (unsigned), the same form model/golden.py returns and the testbench reads from the DUT.

All functions accept a single N x N matrix or a batch of shape (..., N, N).
"""

import numpy as np


def _mask(W):
    return (1 << W) - 1


def expected_checksums(A, B, W):
    """Reference checksums computed from the inputs only: (column checksums, row checksums)."""
    A = np.asarray(A, dtype=np.int64)
    B = np.asarray(B, dtype=np.int64)
    col = np.einsum("...k,...kj->...j", A.sum(axis=-2), B) & _mask(W)
    row = np.einsum("...ik,...k->...i", A, B.sum(axis=-1)) & _mask(W)
    return col, row


def output_checksums(C, W):
    """Checksums of the (possibly wrong) output: (column sums, row sums), mod 2^W."""
    C = np.asarray(C, dtype=np.int64)
    return C.sum(axis=-2) & _mask(W), C.sum(axis=-1) & _mask(W)


def mismatches(C, A, B, W):
    """Boolean arrays (bad_cols, bad_rows): which checksums disagree."""
    exp_col, exp_row = expected_checksums(A, B, W)
    out_col, out_row = output_checksums(C, W)
    return exp_col != out_col, exp_row != out_row


def error_flag(C, A, B, W):
    """True where any checksum disagrees (err_flag in the hardware)."""
    bad_cols, bad_rows = mismatches(C, A, B, W)
    return bad_cols.any(axis=-1) | bad_rows.any(axis=-1)


def check(C, A, B, W):
    """Check one matrix. Returns (err_flag, err_row, err_col).

    err_row and err_col give the location when exactly one row and one column disagree
    (a single wrong element), and are None otherwise.
    """
    bad_cols, bad_rows = mismatches(C, A, B, W)
    flag = bool(bad_cols.any() or bad_rows.any())
    rows, cols = np.flatnonzero(bad_rows), np.flatnonzero(bad_cols)
    if len(rows) == 1 and len(cols) == 1:
        return flag, int(rows[0]), int(cols[0])
    return flag, None, None
