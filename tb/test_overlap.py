"""Overlap ablation for the weight-stationary array.

The weights are loaded once. Then T tiles of A are fed back-to-back into the bare array
(systolic_ws, no control logic), and tile m starts II cycles after tile m-1. II is the
initiation interval:
  II = 11 (3N - 1)  no overlap: a tile starts when the previous one has fully left
  II = N            full overlap: row k of tile m+1 is fed right after row k of tile m
  II < N            too tight: two tiles want the same feed lane in the same cycle

Every result is checked against model/golden.py. For II >= N all T results must be right.
For II < N the test expects wrong results, which shows where the limit is. The counts go to
overlap.txt in the log folder.

Run:  pytest tb/test_overlap.py
"""

import random
from pathlib import Path

import cocotb
import numpy as np
import pytest
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge

from mat_util import pack
from model.golden import matmul_golden
from run_util import WIDTHS, run_cocotb

N = 4
T = 8                                  # tiles per run
INTERVALS = [3, 4, 5, 6, 8, 11]        # II values to try
FULL_RUN = 3 * N - 1                   # cycles one tile needs on its own


async def run_overlap(dut, tiles, B, II, W):
    """Load B, feed the tiles with interval II, return (results, cycles from first load edge)."""
    dut.rst_n.value = 0
    dut.en.value = 1
    dut.load_w.value = 0
    dut.w_top.value = 0
    dut.a_left.value = 0
    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)

    dut.load_w.value = 1
    for c in range(N):                              # last row of B first
        dut.w_top.value = pack(B[N - 1 - c], 8)
        await FallingEdge(dut.clk)
    dut.load_w.value = 0
    dut.w_top.value = 0

    mask = (1 << W) - 1
    results = [np.zeros((N, N), dtype=np.int64) for _ in tiles]
    run_cycles = (len(tiles) - 1) * II + FULL_RUN
    for t in range(run_cycles):
        lanes = [0] * N
        for m, A in enumerate(tiles):               # if two tiles claim a lane, the later wins
            for k in range(N):
                idx = t - m * II - k
                if 0 <= idx < N:
                    lanes[k] = int(A[idx][k])
        dut.a_left.value = pack(lanes, 8)
        bottom = dut.psum_bottom.value.to_unsigned()
        for m in range(len(tiles)):
            for j in range(N):
                i = t - m * II - j - N
                if 0 <= i < N:
                    results[m][i][j] = (bottom >> (W * j)) & mask
        await FallingEdge(dut.clk)
    dut.a_left.value = 0
    return results, N + run_cycles


@cocotb.test()
async def test_overlap(dut):
    W = int(dut.W.value)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    B = [[random.randint(-128, 127) for _ in range(N)] for _ in range(N)]
    tiles = [[[random.randint(-128, 127) for _ in range(N)] for _ in range(N)] for _ in range(T)]
    expected = [matmul_golden(A, B, W) for A in tiles]

    lines = [f"WS overlap ablation, W = {W}, {T} tiles sharing one B, weights loaded once", "",
             f"{'II':>3} {'cycles':>7} {'per tile':>9} {'PE util':>8} {'correct':>9}  note"]
    for II in INTERVALS:
        results, cycles = await run_overlap(dut, tiles, B, II, W)
        right = sum(np.array_equal(r, e) for r, e in zip(results, expected))
        # 64 MACs per tile, 16 PEs; steady-state utilisation is 64 / (16 * II) = 4 / II
        util = 100.0 * (N ** 3) / (N * N * II)
        note = {FULL_RUN: "no overlap", N: "full overlap"}.get(II, "")
        if II < N:
            note = "lane collision"
        util_text = "n/a" if II < N else f"{util:.1f}%"   # meaningless when results are wrong
        lines.append(f"{II:>3} {cycles:>7} {cycles / T:>9.2f} {util_text:>8} "
                     f"{right:>4}/{T}  {note}")
        if II >= N:
            assert right == T, f"II = {II}: only {right} of {T} tiles correct"
        else:
            assert right < T, f"II = {II}: expected lane collisions to break results, got all correct"
    text = "\n".join(lines)
    Path("overlap.txt").write_text(text + "\n")
    dut._log.info("\n" + text)


@pytest.mark.parametrize("W", WIDTHS)
def test_overlap_runner(W):
    run_cocotb("systolic_ws", ["pe.sv", "systolic_ws.sv"], "test_overlap",
               f"overlap_W{W}", parameters={"W": W})
