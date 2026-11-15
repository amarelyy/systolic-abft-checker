"""Fault injection into the PE registers, and the classifier.

Both fault kinds change a register of the running design from the testbench:
  flip   one bit is XORed once at a chosen cycle (a transient, soft error)
  stuck  one bit is forced to 0 or 1 at every cycle of a window (a permanent-like defect that
         lasts for a number of cycles)
Cycle c is counted in falling clock edges after the edge that accepted start (c = 0 is the
first one). A fault applied at cycle c is seen by the logic at the next rising edge, so a flip
at c lives for exactly one cycle unless the design's own logic keeps it.

Classifier (labels as in the project plan, plus one guard label):
  masked              the output C did not change and the error flag stayed low
  detected            C changed and the error flag went high
  missed              C changed and the error flag stayed low
  flag_without_change C did not change but the error flag went high (should never happen)
"""

from dataclasses import dataclass

import numpy as np
from cocotb.triggers import FallingEdge, RisingEdge

from mat_util import pack_matrix, unpack_matrix

N = 4
# Cycle (falling edges after the accepting edge) at which done is high.
C_DONE = {"ws": 15, "os": 10}


@dataclass
class Fault:
    kind: str           # "flip" or "stuck"
    target: object      # tb.targets.Target
    bit: int
    cycle: int          # first cycle the fault is applied
    length: int = 1     # number of cycles (stuck only)
    value: int = 0      # stuck-at value (stuck only)


def classify(changed, flagged):
    if not changed:
        return "flag_without_change" if flagged else "masked"
    return "detected" if flagged else "missed"


def _apply(handle, fault, c):
    """Apply the fault to its register if cycle c is inside its window."""
    if fault.kind == "flip" and c == fault.cycle:
        handle.value = handle.value.to_unsigned() ^ (1 << fault.bit)
    elif fault.kind == "stuck" and fault.cycle <= c < fault.cycle + fault.length:
        word = handle.value.to_unsigned()
        word = (word | (1 << fault.bit)) if fault.value else (word & ~(1 << fault.bit))
        handle.value = word


async def run_multiply(dut, design, A, B, W, fault=None, handles=None):
    """One multiply with an optional fault. Returns a dict with C and the checker outputs."""
    handle = None
    if fault is not None:
        key = fault.target.name
        if handles is not None and key in handles:
            handle = handles[key]
        else:
            handle = fault.target.handle(dut)
            if handles is not None:
                handles[key] = handle

    while dut.busy.value == 1:
        await FallingEdge(dut.clk)
    dut.stall.value = 0
    dut.keep_w.value = 0
    dut.a_mat.value = pack_matrix(A)
    dut.b_mat.value = pack_matrix(B)
    dut.start.value = 1
    await RisingEdge(dut.clk)               # the edge that accepts start
    await FallingEdge(dut.clk)              # cycle 0
    dut.start.value = 0

    c_done = C_DONE[design]
    for c in range(c_done):
        if handle is not None:
            _apply(handle, fault, c)
        await FallingEdge(dut.clk)
    assert dut.done.value == 1, f"done not high at cycle {c_done}"
    C = unpack_matrix(dut.c_mat.value.to_unsigned(), W, N)
    await FallingEdge(dut.clk)              # the checker reports one cycle after done
    assert dut.chk_valid.value == 1, "no check pulse one cycle after done"
    return {
        "C": C,
        "flag": int(dut.err_flag.value),
        "loc_valid": int(dut.err_loc_valid.value),
        "row": int(dut.err_row.value),
        "col": int(dut.err_col.value),
    }
