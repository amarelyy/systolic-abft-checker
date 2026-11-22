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
  flag_without_change C did not change but the error flag went high (a false alarm; with a
                      healthy checker this never happens, with a fault in the checker it can)
  no_result           the control never produced `done` (the array hung); the checker only looks at
                      data, so it cannot see this
"""

from dataclasses import dataclass

import random

import numpy as np
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

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
        handle.value = int(handle.value) ^ (1 << fault.bit)      # int() also works for 1-bit signals
    elif fault.kind == "stuck" and fault.cycle <= c < fault.cycle + fault.length:
        word = int(handle.value)
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


async def reset(dut):
    """Reset the design (two cycles), so every injection starts from a clean state."""
    dut.stall.value = 0
    dut.start.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


async def run_multiply_ext(dut, design, A, B, W, faults=(), handles=None, stall_p=0.0,
                           timeout=80):
    """One multiply from a fresh reset, with any number of faults and optional random stalls.

    Returns a dict; `done` is False if the control never finished within `timeout` cycles.
    Cycle c is counted as in run_multiply. A fault is applied at every falling edge of its window.
    """
    await reset(dut)
    live = []
    for f in faults:
        key = f.target.name
        if handles is not None and key in handles:
            live.append((f, handles[key]))
        else:
            h = f.target.handle(dut)
            if handles is not None:
                handles[key] = h
            live.append((f, h))

    dut.keep_w.value = 0
    dut.a_mat.value = pack_matrix(A)
    dut.b_mat.value = pack_matrix(B)
    dut.start.value = 1
    await RisingEdge(dut.clk)               # the edge that accepts start
    await FallingEdge(dut.clk)              # cycle 0
    dut.start.value = 0

    out = {"done": False, "done_cycle": None, "C": None, "chk_seen": False, "flag": 0,
           "loc_valid": 0, "row": 0, "col": 0}
    for c in range(timeout):
        for f, h in live:
            _apply(h, f, c)
        if stall_p:
            dut.stall.value = int(random.random() < stall_p)
        await FallingEdge(dut.clk)
        if dut.done.value == 1:
            out["done"], out["done_cycle"] = True, c + 1
            out["C"] = unpack_matrix(dut.c_mat.value.to_unsigned(), W, N)
            out["ref_ready"] = int(dut.u_chk.ref_ready.value)       # was the reference finished?
            out["ref_col"] = int(dut.u_chk.ref_col.value)
            out["ref_row"] = int(dut.u_chk.ref_row.value)
            break
    dut.stall.value = 0
    if out["done"]:
        await FallingEdge(dut.clk)          # the checker reports one cycle after done
        out["chk_seen"] = dut.chk_valid.value == 1
        out["flag"] = int(dut.err_flag.value)
        out["loc_valid"] = int(dut.err_loc_valid.value)
        out["row"], out["col"] = int(dut.err_row.value), int(dut.err_col.value)
    return out
