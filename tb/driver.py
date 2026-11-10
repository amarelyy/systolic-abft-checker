"""Stimulus for systolic_ws_ctrl: random matrices, the input driver, and the stall driver."""

import random

import cocotb
from cocotb.triggers import FallingEdge

from mat_util import pack_matrix

N = 4

# Values that random uniform input almost never hits together, mixed into the stimulus.
CORNER_VALUES = [-128, -127, -1, 0, 1, 126, 127]


def random_int8(corner_rate=0.2):
    """One INT8 value: usually uniform over -128..127, sometimes a corner value."""
    if random.random() < corner_rate:
        return random.choice(CORNER_VALUES)
    return random.randint(-128, 127)


def random_matrix(mode=None):
    """One N x N INT8 matrix. The mode is random unless given.

    uniform:  every element from random_int8()
    extreme:  every element is -128 or 127 (largest products)
    sparse:   about 70% zeros (results near zero, many zero-sign products)
    """
    mode = mode or random.choices(["uniform", "extreme", "sparse"], weights=[80, 10, 10])[0]
    if mode == "extreme":
        return [[random.choice([-128, 127]) for _ in range(N)] for _ in range(N)]
    if mode == "sparse":
        return [[random_int8() if random.random() < 0.3 else 0 for _ in range(N)] for _ in range(N)]
    return [[random_int8() for _ in range(N)] for _ in range(N)]


class InputDriver:
    """Sends one (A, B) pair: holds start until the DUT accepts it (busy goes high)."""

    def __init__(self, dut):
        self.dut = dut
        dut.start.value = 0
        dut.a_mat.value = 0
        dut.b_mat.value = 0

    async def send(self, A, B):
        dut = self.dut
        while dut.busy.value == 1:
            await FallingEdge(dut.clk)
        dut.a_mat.value = pack_matrix(A)
        dut.b_mat.value = pack_matrix(B)
        dut.start.value = 1
        await FallingEdge(dut.clk)
        while dut.busy.value == 0:           # not accepted yet, for example stalled
            await FallingEdge(dut.clk)
        dut.start.value = 0
        # Change the inputs right after they are accepted, to check that the DUT latched them.
        dut.a_mat.value = random.getrandbits(8 * N * N)
        dut.b_mat.value = random.getrandbits(8 * N * N)


class StallDriver:
    """Drives stall every cycle. Set .mode between transactions.

    none:   never stall
    random: stall each cycle with probability 0.25
    burst:  mostly no stall, with stall bursts of 1 to 8 cycles
    """

    MODES = ["none", "random", "burst"]

    def __init__(self, dut):
        self.dut = dut
        self.mode = "none"
        dut.stall.value = 0
        self._task = cocotb.start_soon(self._run())

    async def _run(self):
        burst_left = 0
        while True:
            await FallingEdge(self.dut.clk)
            if self.mode == "random":
                stall = random.random() < 0.25
            elif self.mode == "burst":
                if burst_left == 0 and random.random() < 0.1:
                    burst_left = random.randint(1, 8)
                stall = burst_left > 0
                burst_left = max(0, burst_left - 1)
            else:
                stall = False
            self.dut.stall.value = int(stall)
