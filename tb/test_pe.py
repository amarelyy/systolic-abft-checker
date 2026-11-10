"""PE tests (steps 1.4, 1.5).

Run all widths:  pytest tb/test_pe.py
"""

import random

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

from run_util import run_cocotb


async def reset(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.en.value = 1
    dut.load_w.value = 0
    dut.w_in.value = 0
    dut.a_in.value = 0
    dut.psum_in.value = 0
    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


async def load_weight(dut, w):
    dut.load_w.value = 1
    dut.w_in.value = w
    await FallingEdge(dut.clk)
    dut.load_w.value = 0


async def mac(dut, a, psum_in):
    """Apply a and psum_in for one cycle, return psum_out as a W-bit unsigned pattern."""
    dut.a_in.value = a
    dut.psum_in.value = psum_in
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    return dut.psum_out.value.to_unsigned()


@cocotb.test()
async def test_pe_basic(dut):
    """Step 1.4: a=2, w=3, psum_in=1, expect 7."""
    await reset(dut)
    await load_weight(dut, 3)
    got = await mac(dut, 2, 1)
    assert got == 7, f"expected 7, got {got}"


@cocotb.test()
async def test_pe_random(dut):
    """Step 1.5: 1000 random MACs over the full INT8 range and full psum range."""
    W = int(dut.W.value)
    mask = (1 << W) - 1
    await reset(dut)
    w = None
    for i in range(1000):
        if i % 50 == 0:                       # change the weight now and then
            w = random.randint(-128, 127)
            await load_weight(dut, w)
        a = random.randint(-128, 127)
        psum_in = random.randint(0, mask)     # random W-bit pattern, includes overflow cases
        expected = (psum_in + a * w) & mask
        got = await mac(dut, a, psum_in)
        assert got == expected, (
            f"test {i}: a={a} w={w} psum_in={psum_in:#x}: expected {expected:#x}, got {got:#x}")
    dut._log.info("1000 random PE tests passed")


@pytest.mark.parametrize("W", [20, 24, 32])
def test_pe_runner(W):
    run_cocotb("pe", ["pe.sv"], "test_pe", f"pe_W{W}", parameters={"W": W})
