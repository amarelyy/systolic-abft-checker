"""Directed tests for the WS array with control logic (steps 1.11, 1.12, 1.13).

Every result is compared with model/golden.py.

Run:  pytest tb/test_ws_ctrl.py
"""

import random

import cocotb
import numpy as np
import pytest
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

from mat_util import pack_matrix, unpack_matrix
from model.golden import matmul_golden
from run_util import run_cocotb

N = 4
LATENCY = N + 3 * N - 1      # LOAD + RUN cycles, from start to done


async def reset(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.start.value = 0
    dut.a_mat.value = 0
    dut.b_mat.value = 0
    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


async def run_matmul(dut, A, B):
    """Start one multiply, wait for done, return C as unsigned W-bit values."""
    W = int(dut.W.value)
    dut.a_mat.value = pack_matrix(A)
    dut.b_mat.value = pack_matrix(B)
    dut.start.value = 1
    await FallingEdge(dut.clk)
    dut.start.value = 0
    for cycles in range(1, 100):
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        if dut.done.value == 1:
            break
    else:
        raise AssertionError("done never came")
    assert cycles == LATENCY, f"done after {cycles} cycles, expected {LATENCY}"
    return unpack_matrix(dut.c_mat.value.to_unsigned(), W, N)


async def check(dut, name, A, B):
    W = int(dut.W.value)
    got = await run_matmul(dut, A, B)
    expected = matmul_golden(A, B, W)
    assert np.array_equal(got, expected), (
        f"{name}:\nA=\n{np.asarray(A)}\nB=\n{np.asarray(B)}\ngot\n{got}\nexpected\n{expected}")
    dut._log.info(f"{name}: pass")


def full(v):
    return np.full((N, N), v)


@cocotb.test()
async def test_identity(dut):
    """Step 1.11: B = identity, so C must equal A."""
    await reset(dut)
    A = np.arange(N * N).reshape(N, N) - 8          # -8 .. 7, both signs
    await check(dut, "identity", A, np.eye(N, dtype=int))
    W = int(dut.W.value)
    got = await run_matmul(dut, A, np.eye(N, dtype=int))
    assert np.array_equal(got, A & ((1 << W) - 1)), "C != A for B = identity"


@cocotb.test()
async def test_extremes(dut):
    """Step 1.12: all zeros, then -128 and 127 values."""
    await reset(dut)
    await check(dut, "zeros", full(0), full(0))
    await check(dut, "all -128", full(-128), full(-128))   # largest positive result, 4 * 16384
    await check(dut, "all 127", full(127), full(127))
    await check(dut, "-128 x 127", full(-128), full(127))  # most negative result
    await check(dut, "127 x -128", full(127), full(-128))
    checker = np.where((np.indices((N, N)).sum(axis=0) % 2) == 0, 127, -128)
    await check(dut, "checkerboard 127/-128", checker, checker)
    await check(dut, "zeros after extremes", full(0), full(0))   # nothing left over from before


@cocotb.test()
async def test_mixed_signs(dut):
    """Step 1.13: mixed signs, compared with golden.py."""
    await reset(dut)
    signs = np.where(np.random.default_rng(1).random((N, N)) < 0.5, -1, 1)
    await check(dut, "sign pattern", signs * 100, -signs.T * 77)
    for n in range(50):
        A = [[random.randint(-128, 127) for _ in range(N)] for _ in range(N)]
        B = [[random.randint(-128, 127) for _ in range(N)] for _ in range(N)]
        await check(dut, f"random mixed {n}", A, B)


@pytest.mark.parametrize("W", [20, 24, 32])
def test_ws_ctrl_runner(W):
    run_cocotb("systolic_ws_ctrl", ["pe.sv", "systolic_ws.sv", "systolic_ws_ctrl.sv"],
               "test_ws_ctrl", f"ws_ctrl_W{W}", parameters={"W": W})
