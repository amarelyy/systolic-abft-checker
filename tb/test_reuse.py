"""Weight-reuse workload: one B multiplied with many different A, on both designs.

Weight-stationary keeps B in the array, so only the first multiply loads it (keep_w = 0) and
the rest skip the load (keep_w = 1). The B given on the skipped multiplies is random garbage,
so if the RTL read it, the result would be wrong. Output-stationary has no stored weights and
streams B again every time.

Traffic is read from the counters inside the RTL (elements that crossed the array boundary),
and cycles are counted from the first start to the last done. Results go to reuse.txt.

Run:  pytest tb/test_reuse.py
"""

import random
from pathlib import Path

import cocotb
import numpy as np
import pytest
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

from mat_util import pack_matrix, unpack_matrix
from model.golden import matmul_golden
from run_util import DESIGNS, WIDTHS, run_cocotb

N = 4
TILES = [1, 2, 4, 8, 16]      # number of A matrices sharing one B


def rand_matrix():
    return [[random.randint(-128, 127) for _ in range(N)] for _ in range(N)]


async def multiply(dut, A, B, keep_w):
    """Run one multiply, return (C, edges from accepting start to done)."""
    W = int(dut.W.value)
    dut.a_mat.value = pack_matrix(A)
    dut.b_mat.value = pack_matrix(B)
    dut.keep_w.value = int(keep_w)
    dut.start.value = 1
    await RisingEdge(dut.clk)          # this edge accepts start
    await FallingEdge(dut.clk)
    dut.start.value = 0
    edges = 1
    while dut.done.value != 1:
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        edges += 1
        assert edges < 200, "done never came"
    return unpack_matrix(dut.c_mat.value.to_unsigned(), W, N), edges


@cocotb.test()
async def test_reuse(dut):
    W = int(dut.W.value)
    ws = "_ws_" in dut._name
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.stall.value = 0
    dut.start.value = 0
    dut.keep_w.value = 0
    dut.a_mat.value = 0
    dut.b_mat.value = 0
    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)

    lines = [f"design = {'ws' if ws else 'os'}, W = {W}, one B shared by T tiles of A", "",
             f"{'T':>3} {'cycles':>7} {'A read':>7} {'B read':>7} {'C written':>9} {'total moved':>11}"]
    for T in TILES:
        # snapshot the RTL counters and the cycle count before this workload
        a0, b0, c0 = int(dut.cnt_a.value), int(dut.cnt_b.value), int(dut.cnt_c.value)
        B = rand_matrix()
        cycles = 0
        for t in range(T):
            A = rand_matrix()
            keep = ws and t > 0
            C, edges = await multiply(dut, A, rand_matrix() if keep else B, keep)
            assert np.array_equal(C, matmul_golden(A, B, W)), f"T={T} tile {t}: wrong result"
            cycles += edges
            await FallingEdge(dut.clk)
        a, b, c = (int(dut.cnt_a.value) - a0, int(dut.cnt_b.value) - b0,
                   int(dut.cnt_c.value) - c0)
        lines.append(f"{T:>3} {cycles:>7} {a:>7} {b:>7} {c:>9} {a + b + c:>11}")
    text = "\n".join(lines)
    Path("reuse.txt").write_text(text + "\n")
    dut._log.info("\n" + text)


@pytest.mark.parametrize("W", WIDTHS[:1])
@pytest.mark.parametrize("design", DESIGNS)
def test_reuse_runner(design, W):
    top, sources = DESIGNS[design]
    run_cocotb(top, sources, "test_reuse", f"reuse_{design}_W{W}", parameters={"W": W})
