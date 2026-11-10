"""Constrained-random test of the WS array with back-pressure and functional coverage.

Each transaction picks a matrix mode (driver.random_matrix) and a stall mode
(StallDriver.MODES). The monitor reports what the DUT did, the scoreboard checks it against
model/golden.py, and coverage.txt is written to the run's log folder.

Run:  pytest tb/test_random.py          (number of tests: env NUM_TESTS, default 2000)
"""

import os
import random
from pathlib import Path

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge

from func_coverage import Coverage
from driver import InputDriver, StallDriver, random_matrix
from monitor import Monitor
from run_util import WIDTHS, run_cocotb
from scoreboard import Scoreboard

NUM_TESTS = int(os.environ.get("NUM_TESTS", 2000))


@cocotb.test()
async def test_random(dut):
    W = int(dut.W.value)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    driver = InputDriver(dut)
    stall = StallDriver(dut)
    scoreboard = Scoreboard(dut._log, W)
    coverage = Coverage(W)
    done = []

    def on_transaction(tr):
        scoreboard.check(tr)
        coverage.sample(tr)
        done.append(tr)

    # Start the monitor before the first send, or it misses the first transaction.
    Monitor(dut, on_transaction)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)

    for _ in range(NUM_TESTS):
        stall.mode = random.choice(StallDriver.MODES)
        await driver.send(random_matrix(), random_matrix())
    stall.mode = "none"
    for _ in range(200):                     # bounded wait, so a lost transaction fails, not hangs
        if len(done) == NUM_TESTS:
            break
        await FallingEdge(dut.clk)
    assert len(done) == NUM_TESTS, f"monitor saw {len(done)} of {NUM_TESTS} transactions"

    report = coverage.report()
    Path("coverage.txt").write_text(report + "\n")
    dut._log.info("\n" + report)
    dut._log.info(f"{scoreboard.passed} passed, {len(scoreboard.mismatches)} mismatches, "
                  f"{NUM_TESTS} transactions")
    assert not scoreboard.mismatches, f"{len(scoreboard.mismatches)} mismatches, see log"


@pytest.mark.parametrize("W", WIDTHS)
def test_random_runner(W):
    run_cocotb("systolic_ws_ctrl", ["pe.sv", "systolic_ws.sv", "systolic_ws_ctrl.sv"],
               "test_random", f"random_W{W}", parameters={"W": W})
