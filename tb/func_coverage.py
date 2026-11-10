"""Functional coverage model for the WS array.

Written in plain Python so every bin is visible. Each coverpoint has a fixed list of bins,
and its coverage is hit bins / all bins. Total coverage is the average over coverpoints,
each with weight 1, which is how SystemVerilog covergroups compute it by default.

Coverpoints (sampled from what the monitor saw, not from what the driver meant to send):
  a_value, w_value   every INT8 value, -128..127, seen as an A element / B element
  sign_a, sign_w     sign of each multiplied pair a = A[i][k], w = B[k][j]
  sign_a_x_sign_w    cross of the two signs (9 bins)
  overflow           does a C element overflow a signed W-bit register
  stall              where the transaction was stalled: none, load only, run only, both
  start_blocked      start was presented while stall was high
  sign_x_stall       sign_a x sign_w x (stalled or not), 18 bins
  overflow_x_stall   overflow x (stalled or not), 4 bins

Unreachable bins are not chased with more tests. They are listed as excluded, each with the
reason, and left out of the coverage percentage. The raw percentage (nothing excluded) is
reported next to it:
  - overflow = True when no result of an N x N INT8 multiply can overflow W bits,
  - the "load" stall bins for the output-stationary design, which has no load phase.
"""

import itertools

import numpy as np

SIGNS = ["neg", "zero", "pos"]
LOAD, RUN = 1, 2          # FSM state encoding in systolic_ws_ctrl.sv


def can_overflow(W, N):
    """True if some N x N INT8 result does not fit a signed W-bit register."""
    most_pos = N * 128 * 128              # N * (-128 * -128)
    most_neg = -N * 128 * 127             # N * (-128 * 127)
    return most_pos > (1 << (W - 1)) - 1 or most_neg < -(1 << (W - 1))


def _sign(v):
    return "neg" if v < 0 else ("zero" if v == 0 else "pos")


class Coverage:
    def __init__(self, W, N=4, design="ws"):
        self.W, self.N, self.design = W, N, design
        stalled = [False, True]
        self.points = {
            "a_value": list(range(-128, 128)),
            "w_value": list(range(-128, 128)),
            "sign_a": SIGNS,
            "sign_w": SIGNS,
            "sign_a_x_sign_w": list(itertools.product(SIGNS, SIGNS)),
            "overflow": [False, True],
            "stall": ["none", "load", "run", "load+run"],
            "start_blocked": [False, True],
            "sign_x_stall": list(itertools.product(SIGNS, SIGNS, stalled)),
            "overflow_x_stall": list(itertools.product([False, True], stalled)),
        }
        self.hits = {name: dict.fromkeys(bins, 0) for name, bins in self.points.items()}

        self.excluded = {}                    # (coverpoint, bin) -> reason
        if not can_overflow(W, N):
            reason = (f"no {N}x{N} INT8 result can overflow W = {W} "
                      f"(range {-N * 128 * 127} .. {N * 128 * 128}, register holds "
                      f"{-(1 << (W - 1))} .. {(1 << (W - 1)) - 1})")
            self.excluded[("overflow", True)] = reason
            for stalled_flag in stalled:
                self.excluded[("overflow_x_stall", (True, stalled_flag))] = reason
        if design == "os":
            reason = "the output-stationary design has no load phase"
            self.excluded[("stall", "load")] = reason
            self.excluded[("stall", "load+run")] = reason

    def _hit(self, point, value, count=1):
        self.hits[point][value] += count

    def sample(self, tr):
        N, W = self.N, self.W
        for v in tr.A.flatten():
            self._hit("a_value", int(v))
        for v in tr.B.flatten():
            self._hit("w_value", int(v))

        stall = {frozenset(): "none", frozenset({LOAD}): "load", frozenset({RUN}): "run",
                 frozenset({LOAD, RUN}): "load+run"}[frozenset(tr.stalled_in & {LOAD, RUN})]
        stalled = stall != "none"
        self._hit("stall", stall)
        self._hit("start_blocked", tr.stalled_at_start)

        for i, k, j in itertools.product(range(N), repeat=3):
            sa, sw = _sign(tr.A[i][k]), _sign(tr.B[k][j])
            self._hit("sign_a", sa)
            self._hit("sign_w", sw)
            self._hit("sign_a_x_sign_w", (sa, sw))
            self._hit("sign_x_stall", (sa, sw, stalled))

        true_C = tr.A @ tr.B
        lo, hi = -(1 << (W - 1)), (1 << (W - 1)) - 1
        for c in true_C.flatten():
            ov = bool(c < lo or c > hi)
            self._hit("overflow", ov)
            self._hit("overflow_x_stall", (ov, stalled))

    def _bins(self, point, excluded):
        bins = self.hits[point]
        if excluded:
            return bins
        return {b: n for b, n in bins.items() if (point, b) not in self.excluded}

    def percent(self, point, excluded=False):
        """Coverage of one coverpoint. excluded=True counts the excluded bins too (raw)."""
        bins = self._bins(point, excluded)
        return 100.0 * sum(1 for n in bins.values() if n > 0) / len(bins)

    def total(self, excluded=False):
        return float(np.mean([self.percent(p, excluded) for p in self.points]))

    def report(self):
        lines = [f"Functional coverage, design = {self.design}, W = {self.W}", ""]
        lines.append(f"{'coverpoint':<18} {'bins':>5} {'hit':>5} {'coverage':>9} {'raw':>8}")
        for p in self.points:
            bins = self._bins(p, False)
            hit = sum(1 for n in bins.values() if n > 0)
            lines.append(f"{p:<18} {len(bins):>5} {hit:>5} {self.percent(p):>8.1f}% "
                         f"{self.percent(p, True):>7.1f}%")
        lines.append(f"{'TOTAL (average)':<18} {'':>5} {'':>5} {self.total():>8.1f}% "
                     f"{self.total(True):>7.1f}%")
        lines.append("(coverage = excluded bins removed; raw = nothing excluded)")
        lines.append("")
        lines.append("Excluded bins (unreachable):")
        lines += [f"  {p}: {b}: {r}" for (p, b), r in self.excluded.items()] or ["  none"]
        lines.append("")
        lines.append("Reachable bins never hit:")
        missed = [(p, b) for p, bins in self.hits.items() for b, n in bins.items()
                  if n == 0 and (p, b) not in self.excluded]
        lines += [f"  {p}: {b}" for p, b in missed] or ["  none"]
        lines.append("")
        lines.append("Hit counts (small coverpoints):")
        for p, bins in self.hits.items():
            if len(bins) <= 18:
                lines.append(f"  {p}: " + ", ".join(f"{b}={n}" for b, n in bins.items()))
        return "\n".join(lines)
