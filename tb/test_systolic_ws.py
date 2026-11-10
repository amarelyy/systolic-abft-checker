"""Bare WS array test: drive the array edges by hand from Python.

The weight load and the skew are done here in the testbench, not in RTL,
to check the grid wiring before the control logic exists.

Run:  pytest tb/test_systolic_ws.py
"""

import random

import cocotb
import numpy as np
import pytest
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge

from mat_util import pack
from model.golden import matmul_golden
from run_util import WIDTHS, run_cocotb

N = 4


async def hand_fed_matmul(dut, A, B, W):
    """Load B, feed A with skew, and read C from the bottom edge."""
    dut.en.value = 1
    dut.load_w.value = 1
    for c in range(N):                      # row N-1 first, so it ends up at the bottom
        dut.w_top.value = pack(B[N - 1 - c], 8)
        await FallingEdge(dut.clk)
    dut.load_w.value = 0
    dut.w_top.value = 0

    C = np.zeros((N, N), dtype=np.int64)
    mask = (1 << W) - 1
    for t in range(3 * N - 1):
        dut.a_left.value = pack([A[t - k][k] if 0 <= t - k < N else 0 for k in range(N)], 8)
        bottom = dut.psum_bottom.value.to_unsigned()
        for j in range(N):
            i = t - j - N
            if 0 <= i < N:
                C[i][j] = (bottom >> (W * j)) & mask
        await FallingEdge(dut.clk)
    dut.a_left.value = 0
    return C


@cocotb.test()
async def test_hand_fed(dut):
    W = int(dut.W.value)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.en.value = 1
    dut.load_w.value = 0
    dut.w_top.value = 0
    dut.a_left.value = 0
    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)

    for n in range(20):
        A = [[random.randint(-128, 127) for _ in range(N)] for _ in range(N)]
        B = [[random.randint(-128, 127) for _ in range(N)] for _ in range(N)]
        got = await hand_fed_matmul(dut, A, B, W)
        expected = matmul_golden(A, B, W)
        assert np.array_equal(got, expected), f"matrix {n}:\nA={A}\nB={B}\ngot\n{got}\nexpected\n{expected}"
    dut._log.info("20 hand-fed random matrices match golden.py")


@pytest.mark.parametrize("W", WIDTHS)
def test_systolic_ws_runner(W):
    run_cocotb("systolic_ws", ["pe.sv", "systolic_ws.sv"], "test_systolic_ws",
               f"systolic_ws_W{W}", parameters={"W": W})
