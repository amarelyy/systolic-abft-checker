"""Monitor for systolic_ws_ctrl.

Watches the DUT pins only (it never looks at what the driver meant to send) and reports one
transaction per multiply: the A and B the DUT accepted, the C it produced, how many cycles it
took, and where it was stalled.

Sampling is done in ReadOnly after the falling edge, so it sees the values the DUT will sample
at the next rising edge.
"""

from dataclasses import dataclass, field

import cocotb
import numpy as np
from cocotb.triggers import FallingEdge, ReadOnly

from mat_util import unpack, unpack_matrix

N = 4


def _as_int8_matrix(word):
    vals = [v - 256 if v > 127 else v for v in unpack(word, 8, N * N)]
    return np.array(vals, dtype=np.int64).reshape(N, N)


@dataclass
class Transaction:
    A: np.ndarray
    B: np.ndarray
    C: np.ndarray = None
    cycles: int = 0                 # rising edges from the accepting edge (included) to done
    stall_cycles: int = 0           # busy cycles with stall high
    stalled_at_start: bool = False  # start was presented but held off by stall
    stalled_in: set = field(default_factory=set)   # FSM states that saw a stall


class Monitor:
    def __init__(self, dut, callback):
        self.dut = dut
        self.callback = callback
        self._task = cocotb.start_soon(self._run())

    async def _run(self):
        dut = self.dut
        W = int(dut.W.value)
        tr = None
        start_blocked = False
        while True:
            await FallingEdge(dut.clk)
            await ReadOnly()
            busy, stall, start = dut.busy.value, dut.stall.value, dut.start.value

            if tr is not None:
                tr.cycles += 1
                if busy == 1 and stall == 1:
                    tr.stall_cycles += 1
                    tr.stalled_in.add(int(dut.state.value))
                if dut.done.value == 1:
                    tr.C = unpack_matrix(dut.c_mat.value.to_unsigned(), W, N)
                    self.callback(tr)
                    tr = None

            if busy == 0 and start == 1:
                if stall == 1:
                    start_blocked = True
                elif tr is None:
                    # Accepted at the next rising edge.
                    tr = Transaction(A=_as_int8_matrix(dut.a_mat.value.to_unsigned()),
                                     B=_as_int8_matrix(dut.b_mat.value.to_unsigned()),
                                     stalled_at_start=start_blocked)
                    start_blocked = False
