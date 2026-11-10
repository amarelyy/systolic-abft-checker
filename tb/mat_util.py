"""Pack and unpack matrices for the flat buses of the array (element [r][c] at index r*N + c)."""

import numpy as np


def pack(values, width):
    """Pack a flat list of signed ints into one int, element 0 in the lowest bits."""
    mask = (1 << width) - 1
    out = 0
    for idx, v in enumerate(values):
        out |= (int(v) & mask) << (width * idx)
    return out


def unpack(word, width, count):
    """Unpack an int into a list of unsigned width-bit values, element 0 from the lowest bits."""
    mask = (1 << width) - 1
    return [(word >> (width * idx)) & mask for idx in range(count)]


def pack_matrix(M):
    """Pack an N x N INT8 matrix into an a_mat / b_mat bus value."""
    return pack(np.asarray(M).flatten(), 8)


def unpack_matrix(word, W, N):
    """Unpack a c_mat bus value into an N x N array of unsigned W-bit values."""
    return np.array(unpack(word, W, N * N), dtype=np.int64).reshape(N, N)
