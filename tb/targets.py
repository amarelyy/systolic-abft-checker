"""Registers inside the PE arrays that faults are injected into.

Weight-stationary PE (rtl/pe.sv):   psum_out (W bits), a_out (8 bits), w (8 bits)
Output-stationary PE (rtl/pe_os.sv): acc (W bits),      a_out (8 bits), b_out (8 bits)

Each target is one register of one PE, reached through the simulator's hierarchy. A register
whose width is W holds an accumulated value that always fits in ACC_BITS signed bits (the
largest 4x4 INT8 result is 65536), so bits ACC_BITS .. W-1 are copies of the sign bit. Those
"ghost" bits exist in simulation, but synthesis merges them into one flip-flop, so faults in
them are reported separately.
"""

from dataclasses import dataclass

N = 4
ACC_BITS = 18          # bits needed for any 4x4 INT8 result (-65024 .. 65536)

# design -> (generate block of top.sv, [(register name, class name, is accumulator)])
REGISTERS = {
    "ws": ("g_ws", [("psum_out", "acc", True), ("a_out", "a", False), ("w", "w", False)]),
    "os": ("g_os", [("acc", "acc", True), ("a_out", "a", False), ("b_out", "b", False)]),
}


@dataclass(frozen=True)
class Target:
    design: str
    reg: str            # register name inside the PE
    cls: str            # acc / a / w / b
    row: int
    col: int
    width: int          # number of bits
    is_acc: bool

    @property
    def name(self):
        return f"pe[{self.row}][{self.col}].{self.reg}"

    def handle(self, dut):
        block = REGISTERS[self.design][0]
        node = getattr(dut, block).u_ctrl.u_array
        node = getattr(node, "g_row")[self.row]
        node = getattr(node, "g_col")[self.col]
        return getattr(node.u_pe, self.reg)

    def is_ghost(self, bit):
        """True for a bit of an accumulator register that only copies the sign bit."""
        return self.is_acc and bit >= ACC_BITS


@dataclass(frozen=True)
class FlopTarget:
    """A register of the control logic or of the checker, reached by a path of names.

    Unlike the PE targets above, these are chosen with every flip-flop equally likely, so a
    128-bit register is hit 128 times more often than a 1-bit one.
    """
    design: str
    group: str          # "ctrl" or "chk"
    reg: str
    width: int

    @property
    def name(self):
        return f"{self.group}.{self.reg}"

    def handle(self, dut):
        if self.group == "ctrl":
            node = getattr(getattr(dut, REGISTERS[self.design][0]), "u_ctrl")
        else:
            node = dut.u_chk
        return getattr(node, self.reg)


def ctrl_targets(design, W):
    """Control-logic registers. The OS result is a wire from the PE accumulators, not a register."""
    regs = [("state", 2), ("cnt", 4), ("a_q", 128), ("b_q", 128), ("done", 1)]
    if design == "ws":
        regs.append(("c_mat", 16 * W))                 # the captured result of the WS control
    return [FlopTarget(design, "ctrl", r, w) for r, w in regs]


def chk_targets(design, W):
    """Registers of the ABFT checker."""
    regs = [("a_q", 128), ("b_q", 128), ("ref_col", 4 * W), ("ref_row", 4 * W), ("ref_k", 2),
            ("ref_run", 1), ("ref_ready", 1), ("chk_valid", 1), ("err_flag", 1),
            ("err_loc_valid", 1), ("err_row", 2), ("err_col", 2)]
    return [FlopTarget(design, "chk", r, w) for r, w in regs]


def targets(design, W):
    block, regs = REGISTERS[design]
    return [Target(design, reg, cls, r, c, W if is_acc else 8, is_acc)
            for r in range(N) for c in range(N) for reg, cls, is_acc in regs]
