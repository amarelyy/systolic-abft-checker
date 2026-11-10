"""Scoreboard: checks every monitored transaction against model/golden.py.

Two checks per transaction:
  1. C equals matmul_golden(A, B, W), bit for bit.
  2. Latency: 4N rising edges, counting the edge that accepts start, plus one per stalled
     busy cycle. (That is the 4N - 1 cycles after the accepting edge from the RTL header.)
Every mismatch is logged with the full matrices so it can be reproduced.
"""

import numpy as np

from model.golden import matmul_golden

N = 4
BASE_LATENCY = 4 * N


class Scoreboard:
    def __init__(self, log, W):
        self.log = log
        self.W = W
        self.passed = 0
        self.mismatches = []

    def check(self, tr):
        expected = matmul_golden(tr.A, tr.B, self.W)
        errors = []
        if not np.array_equal(tr.C, expected):
            bad = np.argwhere(tr.C != expected).tolist()
            errors.append(f"C mismatch at [row, col] {bad}")
        expected_cycles = BASE_LATENCY + tr.stall_cycles
        if tr.cycles != expected_cycles:
            errors.append(f"latency {tr.cycles} cycles, expected {expected_cycles} "
                          f"({BASE_LATENCY} + {tr.stall_cycles} stalled)")
        if errors:
            n = len(self.mismatches)
            self.mismatches.append(tr)
            self.log.error(f"MISMATCH #{n}: {'; '.join(errors)}\n"
                           f"A=\n{tr.A}\nB=\n{tr.B}\ngot C=\n{tr.C}\nexpected C=\n{expected}")
        else:
            self.passed += 1
