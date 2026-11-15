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


def targets(design, W):
    block, regs = REGISTERS[design]
    return [Target(design, reg, cls, r, c, W if is_acc else 8, is_acc)
            for r in range(N) for c in range(N) for reg, cls, is_acc in regs]
