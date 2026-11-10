"""Golden model tests (step 1.8).

Run:  pytest tb/test_golden.py
"""

import numpy as np

from model.golden import matmul_golden, to_signed


def test_2x2_example():
    A = [[1, 2], [3, 4]]
    B = [[5, 6], [7, 8]]
    assert matmul_golden(A, B, 32).tolist() == [[19, 22], [43, 50]]


def test_negative_result_wraps_to_W_bits():
    # 1 x -1 = -1, which is all ones in W bits
    assert matmul_golden([[1]], [[-1]], 20).tolist() == [[(1 << 20) - 1]]
    assert to_signed(matmul_golden([[1]], [[-1]], 20), 20).tolist() == [[-1]]


def test_overflow_wraps_like_hardware():
    # 4 x (-128 * -128) = 65536 fits in 20 bits; in 16 bits it would wrap to 0.
    A = np.full((4, 4), -128)
    assert matmul_golden(A, A, 20)[0, 0] == 65536
    assert matmul_golden(A, A, 16)[0, 0] == 0
