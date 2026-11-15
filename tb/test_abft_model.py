"""Tests of the ABFT checksum model (model/abft.py). Pure Python, no simulator.

  - the checksum identity holds for 100 random matrices without wrap-around,
  - with wrap-around mod 2^W it still holds, including matrices that really overflow (W = 16),
  - a single wrong element is detected and located exactly,
  - a reference that saturates instead of wrapping causes false alarms (so the reference
    model must wrap exactly like the hardware),
  - four errors in a rectangle can cancel and go undetected (the known limit).

Run:  pytest tb/test_abft_model.py
"""

import itertools

import numpy as np
import pytest

from model.abft import check, error_flag
from model.golden import matmul_golden

N = 4
rng = np.random.default_rng(12345)


def random_batch(M):
    """M pairs of INT8 matrices: uniform, extreme (-128 / 127) and sparse kinds mixed."""
    A = rng.integers(-128, 128, size=(M, N, N))
    B = rng.integers(-128, 128, size=(M, N, N))
    kind = rng.integers(0, 10, size=M)
    ext = np.where(rng.random((M, N, N)) < 0.5, -128, 127)
    sparse = rng.random((M, N, N)) < 0.7
    for X in (A, B):
        X[kind == 0] = ext[kind == 0]
        X[kind == 1] = np.where(sparse, 0, X)[kind == 1]
    return A, B


def test_identity_without_wrap_100_matrices():
    A, B = random_batch(100)
    C = A @ B                                   # exact integers, no wrap
    assert np.array_equal(C.sum(axis=-2), np.einsum("mk,mkj->mj", A.sum(axis=-2), B))
    assert np.array_equal(C.sum(axis=-1), np.einsum("mik,mk->mi", A, B.sum(axis=-1)))


@pytest.mark.parametrize("W", [16, 17, 18, 32])
def test_no_false_alarm_with_wrap(W):
    A, B = random_batch(5000)
    C = np.stack([matmul_golden(a, b, W) for a, b in zip(A, B)])
    assert not error_flag(C, A, B, W).any()


def test_wrap_case_really_overflows_at_w16():
    A = np.full((N, N), -128)
    C = matmul_golden(A, A, 16)                 # 4 x 16384 = 65536 wraps to 0 in 16 bits
    assert (C == 0).all()
    assert check(C, A, A, 16) == (False, None, None)


@pytest.mark.parametrize("W", [16, 18])
def test_single_error_detected_and_located(W):
    A, B = random_batch(20)
    for a, b in zip(A, B):
        C = matmul_golden(a, b, W)
        for i, j, bit in itertools.product(range(N), range(N), range(W)):
            bad = C.copy()
            bad[i, j] ^= 1 << bit
            assert check(bad, a, b, W) == (True, i, j), (i, j, bit)


def test_saturating_reference_gives_false_alarms():
    W = 16
    A = np.full((N, N), -128)                   # every result is 65536, out of range for W = 16
    lo, hi = -(1 << (W - 1)), (1 << (W - 1)) - 1
    saturated = np.clip(A @ A, lo, hi) & ((1 << W) - 1)
    assert check(saturated, A, A, W)[0], "saturation should break the checksums"


def test_rectangle_of_four_errors_is_undetected():
    W = 18
    A, B = random_batch(1)
    C = matmul_golden(A[0], B[0], W)
    bad = C.copy()
    d = 1 << 5
    for (i, j), s in {(0, 0): d, (0, 1): -d, (1, 0): -d, (1, 1): d}.items():
        bad[i, j] = (bad[i, j] + s) & ((1 << W) - 1)
    assert not np.array_equal(bad, C)
    assert check(bad, A[0], B[0], W) == (False, None, None)
