"""Pre-study for choosing the W sweep: how often does a 4x4 INT8 result overflow W bits?

Overflow here means the true result does not fit in a signed W-bit register, so the
hardware value (wrapped mod 2^W) differs from the true value.

Run:  python model/overflow_study.py [log_dir]
"""

import sys
from pathlib import Path

import numpy as np

N = 4
TRIALS = 1_000_000
SEED = 12345
WIDTHS = [16, 17, 18, 20, 24, 32]


def overflows(C, W):
    lo, hi = -(1 << (W - 1)), (1 << (W - 1)) - 1
    return (C < lo) | (C > hi)


def main():
    rng = np.random.default_rng(SEED)
    A = rng.integers(-128, 128, size=(TRIALS, N, N), dtype=np.int64)
    B = rng.integers(-128, 128, size=(TRIALS, N, N), dtype=np.int64)
    C = A @ B
    corner = {
        "all -128 x all -128": np.full((N, N), -128) @ np.full((N, N), -128),
        "all 127 x all 127": np.full((N, N), 127) @ np.full((N, N), 127),
        "all -128 x all 127": np.full((N, N), -128) @ np.full((N, N), 127),
    }

    lines = [f"N={N}, uniform random INT8 A and B, {TRIALS} matrices, seed {SEED}",
             f"true C range seen: {C.min()} .. {C.max()}",
             f"worst case possible: {-128 * 127 * N} .. {128 * 128 * N}",
             "",
             f"{'W':>3} {'signed range':>26} {'elements overflowed':>20} {'matrices with >=1':>18}  corner cases that overflow"]
    for W in WIDTHS:
        ov = overflows(C, W)
        rng_str = f"{-(1 << (W - 1))} .. {(1 << (W - 1)) - 1}"
        corners = [name for name, M in corner.items() if overflows(M, W).any()]
        lines.append(f"{W:>3} {rng_str:>26} {ov.mean():>19.4%} {ov.any(axis=(1, 2)).mean():>17.4%}  "
                     f"{', '.join(corners) or 'none'}")
    text = "\n".join(lines)
    print(text)
    if len(sys.argv) > 1:
        Path(sys.argv[1], "overflow_study.txt").write_text(text + "\n")


if __name__ == "__main__":
    main()
