"""Tests of the ABFT checker hardware (top = array + control + checker), both dataflows.

  test_no_false_alarms   many fault-free multiplies with random stalls: err_flag must stay low,
                         including multiplies whose results really overflow (W = 16). Also checks
                         that every multiply gives exactly one chk_valid pulse, one cycle after
                         done, and that the flag, row and column match model/abft.py.
  test_single_errors     one wrong element at every position and every bit flip: detected, and
                         the reported row and column are exactly the wrong element.
  test_multiple_errors   random patterns of 2 to 6 wrong elements, and the four-corner
                         rectangle that cancels: hardware must agree with model/abft.py in
                         every case, and the rectangle must go undetected.
  test_keep_w            weight-stationary only: multiplies that reuse the loaded B (the B on
                         the bus is garbage) must not raise false alarms.

The wrong value is added to c_mat by top.sv (simulation-only inj_add); the testbench computes
what the checker should say from the model, using the C the monitor actually saw.
Results go to checker.txt in the run's log folder.

Run:  pytest tb/test_abft_hw.py        (env FREE_RUNS sets the fault-free count, default 10000)
"""

import os
import random
from pathlib import Path

import cocotb
import numpy as np
import pytest
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

from driver import InputDriver, StallDriver, random_matrix
from mat_util import pack, pack_matrix
from model.abft import check
from model.golden import matmul_golden
from monitor import Monitor
from run_util import WIDTHS, run_cocotb

N = 4
FREE_RUNS = int(os.environ.get("FREE_RUNS", 10000))
report_lines = []


def note(dut, text):
    dut._log.info(text)
    report_lines.append(text)


def save_report():
    Path("checker.txt").write_text("\n".join(report_lines) + "\n")


class Bench:
    """Clock, reset, driver, monitor and a watcher of the checker outputs."""

    def __init__(self, dut):
        self.dut = dut
        self.W = int(dut.W.value)
        self.ws = int(dut.DATAFLOW.value) == 0
        self.transactions = []
        self.checks = []                       # (cycles after done, flag, loc_valid, row, col)
        self.problems = []

    async def start(self):
        dut = self.dut
        cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
        self.driver = InputDriver(dut)
        self.stall = StallDriver(dut)
        Monitor(dut, self.transactions.append)
        cocotb.start_soon(self._watch())
        dut.rst_n.value = 0
        await ClockCycles(dut.clk, 2)
        dut.rst_n.value = 1
        await FallingEdge(dut.clk)

    async def _watch(self):
        """Record every chk_valid pulse, and how many cycles after done it came."""
        dut = self.dut
        since_done = None
        while True:
            await FallingEdge(dut.clk)
            if since_done is not None:
                since_done += 1
            if dut.done.value == 1:
                if since_done is not None:
                    self.problems.append("done came again before chk_valid")
                since_done = 0
            if dut.chk_valid.value == 1:
                if since_done is None:
                    self.problems.append("chk_valid without a done before it")
                else:
                    self.checks.append((since_done, int(dut.err_flag.value),
                                        int(dut.err_loc_valid.value),
                                        int(dut.err_row.value), int(dut.err_col.value)))
                since_done = None

    async def multiply(self, A, B, delta=None):
        """Send one multiply, optionally with an error pattern added to C, and wait for its check."""
        dut = self.dut
        n_tr, n_chk = len(self.transactions), len(self.checks)
        dut.inj_add.value = pack(delta.flatten(), self.W) if delta is not None else 0
        await self.driver.send(A, B)
        for _ in range(400):
            await FallingEdge(dut.clk)
            if len(self.checks) > n_chk:
                break
        assert len(self.checks) == n_chk + 1 and len(self.transactions) == n_tr + 1, \
            "multiply or check did not finish"
        dut.inj_add.value = 0
        return self.transactions[-1], self.checks[-1]

    def expected(self, tr):
        """What the checker must say for this multiply, from the model and the C the monitor saw."""
        return check(tr.C, tr.A, tr.B, self.W)

    def agrees(self, tr, chk):
        """Does the hardware result equal the model? Returns an error text or None."""
        _, flag, loc, row, col = chk
        m_flag, m_row, m_col = self.expected(tr)
        if bool(flag) != m_flag:
            return f"err_flag hw={flag} model={m_flag}"
        if m_row is not None and not (loc == 1 and row == m_row and col == m_col):
            return f"location hw=({loc},{row},{col}) model=({m_row},{m_col})"
        if m_row is None and loc == 1:
            return "hw gave a location, model gave none"
        return None


def overflowed(tr, W):
    c = tr.A @ tr.B
    return bool(((c < -(1 << (W - 1))) | (c > (1 << (W - 1)) - 1)).any())


@cocotb.test()
async def test_no_false_alarms(dut):
    bench = Bench(dut)
    await bench.start()
    for _ in range(FREE_RUNS):
        bench.stall.mode = random.choice(StallDriver.MODES)
        await bench.driver.send(random_matrix(), random_matrix())
    bench.stall.mode = "none"
    for _ in range(400):
        if len(bench.checks) == FREE_RUNS:
            break
        await FallingEdge(dut.clk)
    W = bench.W
    trs = bench.transactions
    n_over = sum(overflowed(t, W) for t in trs)
    flagged = sum(c[1] for c in bench.checks)
    delays = sorted({c[0] for c in bench.checks})
    disagree = [(i, bench.agrees(t, c)) for i, (t, c) in enumerate(zip(trs, bench.checks))
                if bench.agrees(t, c)]
    name = "ws" if bench.ws else "os"
    note(dut, f"[{name} W={W}] fault-free multiplies: {len(trs)}, checks seen: {len(bench.checks)}, "
              f"multiplies whose results overflow: {n_over}, false alarms: {flagged}")
    note(dut, f"[{name} W={W}] cycles from done to chk_valid: {delays}; "
              f"disagreements with model: {len(disagree)}; protocol problems: {len(bench.problems)}")
    save_report()
    assert len(trs) == FREE_RUNS and len(bench.checks) == FREE_RUNS
    assert flagged == 0, f"{flagged} false alarms"
    assert not disagree, disagree[:3]
    assert not bench.problems, bench.problems[:3]
    assert delays == [1], f"expected the check one cycle after done, got {delays}"
    if W == 16:
        assert n_over > 0, "W = 16 should produce overflowing multiplies"


@cocotb.test()
async def test_single_errors(dut):
    bench = Bench(dut)
    await bench.start()
    W = bench.W
    name = "ws" if bench.ws else "os"
    tried = detected = located = 0
    for _ in range(3):                                   # three matrix pairs
        A, B = random_matrix(), random_matrix()
        C = matmul_golden(A, B, W)
        for i in range(N):
            for j in range(N):
                for bit in range(W):
                    delta = np.zeros((N, N), dtype=np.int64)
                    delta[i, j] = (int(C[i, j]) ^ (1 << bit)) - int(C[i, j])
                    tr, chk = await bench.multiply(A, B, delta)
                    assert tr.C[i, j] == int(C[i, j]) ^ (1 << bit), "injection did not land"
                    tried += 1
                    detected += chk[1]
                    located += int(chk[2] == 1 and chk[3] == i and chk[4] == j)
    note(dut, f"[{name} W={W}] single wrong element, every position and bit: {tried} injected, "
              f"{detected} detected, {located} located exactly")
    save_report()
    assert detected == tried and located == tried


@cocotb.test()
async def test_multiple_errors(dut):
    bench = Bench(dut)
    await bench.start()
    W = bench.W
    mask = (1 << W) - 1
    name = "ws" if bench.ws else "os"
    counts = {}                                           # pattern -> [tried, detected, mismatches with model]

    async def run(label, delta):
        A, B = random_matrix(), random_matrix()
        tr, chk = await bench.multiply(A, B, delta)
        row = counts.setdefault(label, [0, 0, 0])
        row[0] += 1
        row[1] += chk[1]
        row[2] += int(bench.agrees(tr, chk) is not None)

    for _ in range(300):
        for k in (2, 3, 4, 5, 6):
            delta = np.zeros((N, N), dtype=np.int64)
            for pos in random.sample(range(N * N), k):
                delta[pos // N, pos % N] = random.choice([-1, 1]) * (1 << random.randrange(W - 1))
            await run(f"{k} random errors", delta)
    for _ in range(300):                                   # +d, -d, -d, +d at four corners
        r = random.sample(range(N), 2)
        c = random.sample(range(N), 2)
        d = 1 << random.randrange(W - 1)
        delta = np.zeros((N, N), dtype=np.int64)
        delta[r[0], c[0]] += d
        delta[r[1], c[1]] += d
        delta[r[0], c[1]] -= d
        delta[r[1], c[0]] -= d
        await run("rectangle +d -d -d +d", delta)

    note(dut, f"[{name} W={W}] {'pattern':<24} {'tried':>6} {'detected':>9} {'differs from model':>19}")
    for label, (tried, det, diff) in counts.items():
        note(dut, f"[{name} W={W}] {label:<24} {tried:>6} {det:>9} {diff:>19}")
    save_report()
    assert all(diff == 0 for _, _, diff in counts.values()), "hardware differs from the model"
    assert counts["rectangle +d -d -d +d"][1] == 0, "a cancelling rectangle should go undetected"
    for k in (2, 3):
        assert counts[f"{k} random errors"][1] == counts[f"{k} random errors"][0]


@cocotb.test()
async def test_keep_w(dut):
    bench = Bench(dut)
    if not bench.ws:
        dut._log.info("keep_w applies to the weight-stationary array only; skipped")
        return
    await bench.start()
    W, flagged, n = bench.W, 0, 0
    for T in (2, 4, 8):
        B = random_matrix()
        for t in range(T):
            A = random_matrix()
            n_chk = len(bench.checks)
            dut.keep_w.value = int(t > 0)
            dut.a_mat.value = pack_matrix(A)
            dut.b_mat.value = pack_matrix(B if t == 0 else random_matrix())   # garbage when kept
            dut.start.value = 1
            await RisingEdge(dut.clk)
            await FallingEdge(dut.clk)
            dut.start.value = 0
            for _ in range(200):
                await FallingEdge(dut.clk)
                if len(bench.checks) > n_chk:
                    break
            assert len(bench.checks) == n_chk + 1
            c = matmul_golden(A, B, W)
            assert np.array_equal(bench.transactions[-1].C, c), "array result is wrong with keep_w"
            flagged += bench.checks[-1][1]
            n += 1
    note(dut, f"[ws W={W}] weight reuse (B on the bus is garbage after the first tile): "
              f"{n} multiplies, false alarms: {flagged}")
    save_report()
    assert flagged == 0


DESIGNS_TOP = {"ws": 0, "os": 1}
SOURCES = ["pe.sv", "systolic_ws.sv", "systolic_ws_ctrl.sv", "pe_os.sv", "systolic_os.sv",
           "systolic_os_ctrl.sv", "abft_checker.sv", "top.sv"]


@pytest.mark.parametrize("W", WIDTHS)
@pytest.mark.parametrize("design", DESIGNS_TOP)
def test_abft_hw_runner(design, W):
    run_cocotb("top", SOURCES, "test_abft_hw", f"abft_hw_{design}_W{W}",
               parameters={"W": W, "DATAFLOW": DESIGNS_TOP[design]})
