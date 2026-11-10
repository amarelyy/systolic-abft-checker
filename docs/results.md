# Results

Every number here names the log file it came from. All runs use W = 18 and seed 12345
unless stated otherwise. Tool versions are in `docs/tools.md`.

## Verification of the WS array (constrained-random, with back-pressure)

### Setup

- **DUT:** `systolic_ws_ctrl` (4x4 weight-stationary array plus control), W = 18.
- **Stimulus** (`tb/driver.py`): 2000 multiplies. Each matrix is one of three kinds:
  uniform (80%), extreme (every element -128 or 127, 10%), sparse (about 70% zeros, 10%).
  Inside "uniform", 20% of elements are taken from a corner list
  (-128, -127, -1, 0, 1, 126, 127) and the rest are uniform over -128..127.
- **Back-pressure** (`StallDriver`): for each multiply, one of three stall modes is picked:
  none, random (stall with probability 0.25 every cycle), or burst (stall bursts of 1 to 8
  cycles). While `stall` is high the whole array and FSM hold their state.
- **Checking** (`tb/monitor.py`, `tb/scoreboard.py`): the monitor only watches DUT pins.
  The scoreboard checks every C against `model/golden.py` bit for bit, and checks that the
  latency is exactly 16 edges plus one per stalled busy cycle. After start is accepted, the
  driver puts random garbage on the input buses to check that the DUT latched its inputs.
- **Coverage** (`tb/func_coverage.py`): 10 coverpoints. Total = average of coverpoints with
  equal weight, which is the default way SystemVerilog covergroups compute coverage
  (IEEE 1800-2017, clause 19).

### Result

Log: `logs/2026-11-10T190319_random_W18/` (`sim.log`, `coverage.txt`).
A second run with the same seed (`logs/2026-11-10T190204_random_W18/`) gave identical
coverage numbers, so the run is reproducible.

**2000 of 2000 multiplies passed, 0 mismatches** (C and latency).

| Coverpoint | Bins | Hit | Coverage |
|---|---|---|---|
| a_value (every INT8 value as an A element) | 256 | 256 | 100% |
| w_value (every INT8 value as a B element) | 256 | 256 | 100% |
| sign_a | 3 | 3 | 100% |
| sign_w | 3 | 3 | 100% |
| sign_a x sign_w | 9 | 9 | 100% |
| overflow | 2 | 1 | **50%** |
| stall (none / load / run / load+run) | 4 | 4 | 100% |
| start_blocked (start held off by stall) | 2 | 2 | 100% |
| sign_a x sign_w x stalled | 18 | 18 | 100% |
| overflow x stalled | 4 | 2 | **50%** |
| **Total (average)** | | | **90.0%** |

Bins never hit: `overflow = True`, and both `overflow x stalled` bins with overflow = True.

### Checking the testbench itself (mutation test)

A testbench that always passes proves nothing unless it can also fail. Following the idea of
mutation testing (DeMillo, Lipton and Sayward, 1978), five bugs were planted one at a time in
a copy of the RTL, and the same random test (300 multiplies) was run on each.
Logs: `logs/*_mutant_*`.

| Mutant | Planted bug | Caught? | How |
|---|---|---|---|
| m1 | PEs ignore stall (`en` always 1) | yes, 165 of 300 | C mismatch |
| m2 | FSM keeps counting in RUN while stalled | yes, 172 of 300 | C mismatch |
| m3 | start accepted while stalled | yes | monitor saw 270 of 300 transactions |
| m4 | skew feeds the wrong column of A | yes, 300 of 300 | C mismatch |
| m5 | array reads the input bus instead of the latched copy | yes, 300 of 300 | C mismatch |

All 5 were caught. The m1 and m2 counts (about 55%) match the share of multiplies that were
stalled during RUN at all: in the clean run, 1094 of 2000 (55%) were stalled in RUN.
A multiply that is never stalled cannot show these bugs.

## Analysis

### Why the design passes

The stall is a single clock enable that freezes every register at once: all PEs, the FSM
counter and the capture logic. A systolic array works because all cells move in lock-step
with one global clock (Kung, 1982), and the skew only fixes the *relative* timing between
cells. If every cell skips the same cycle, the relative timing is unchanged, so a stalled
cycle has exactly the same effect as a cycle that never happened. That is why C is correct
for any stall pattern, and why latency grows by exactly one cycle per stall.

The mutants show the other side. m1 (only the FSM stops) and m2 (only the PEs stop) each
freeze *part* of the design, which breaks the relative timing, and the results are wrong
in every multiply that was stalled during RUN.

This scheme is simple but has a known cost: one enable signal drives every register, which is
a very high fanout net. For a 4x4 array this is fine; larger arrays usually use local
handshakes or buffers instead.

### Why coverage is 90% and not 100%

The two missing bins are **unreachable**, not untested. With W = 18, no result can overflow:
the largest possible result is 4 x 16384 = 65536 and the smallest is -65024, while an 18-bit
signed register holds -131072 .. 131071 (see `docs/notes.md`). So `overflow = True` cannot be
hit by any input. Without these bins, every reachable bin is hit (100%).

Coverage literature treats this case explicitly: a coverage model can contain bins that the
design can never reach, and they should be marked as excluded with a written reason, not
"closed" by more random tests (Piziali, 2004). SystemVerilog has `ignore_bins` and
`illegal_bins` for this (IEEE 1800-2017). Excluding them with this proof will be added later.

Overflow behaviour itself is still tested where it can happen: the PE random test feeds
random 18-bit `psum_in` values, so the PE adder wraps in many of those tests.

### Why stimulus shaping was needed

With plain uniform random input, each value has probability 1/256, so zeros and exact
corner values are rare. In this run, the "zero" sign bin got 12,740 of 128,000 pairs
(about 10%), against about 0.4% for pure uniform input. That came from the sparse mode and
the corner list. This is the usual argument for constrained-random rather than pure random
stimulus: the distribution is shaped so that interesting cases happen often
(Spear and Tumbush, 2012).

For the 256-bin value coverpoints, the coupon-collector estimate says about
256 x H(256) ≈ 1,570 random values are needed to see all 256, which is about 100 matrices.
2000 multiplies is about 20 times that, so full value coverage was expected.

The stall bins are uneven (none 735, load only 171, run only 511, load+run 583). This is
expected: LOAD lasts 4 cycles and RUN 11, so a random stall lands in RUN far more often.
With the random mode (p = 0.25), the chance of no stall in all 11 RUN cycles is
0.75^11 ≈ 4%, so "load only" comes almost entirely from the burst mode.

### Bugs found

Two bugs were found, both in the testbench, not in the RTL. See `docs/bug_log.md`.

### Limits

- Verilator is 2-state (no X values), so bugs that only show as X (for example a register
  without reset) cannot be seen here. Every register in the RTL has a synchronous reset.
- The mutation test uses 5 hand-picked bugs. It shows the testbench can catch these bug
  types, not that it catches every bug. An automatic mutation tool (for example MCY, which
  is in the OSS CAD Suite) would give a fuller picture.
- Coverage is sampled at the transaction level (the A, B and C the monitor saw), not inside
  each PE.

## WS vs OS

Not measured yet. Will be added later.

## Detection coverage and false alarms

Not measured yet. Will be added later.

## Overhead of the checker

Not measured yet. Will be added later.

## References

- H. T. Kung, "Why systolic architectures?", *IEEE Computer*, vol. 15, no. 1, 1982.
- N. P. Jouppi et al., "In-Datacenter Performance Analysis of a Tensor Processing Unit",
  *ISCA*, 2017.
- B. Jacob et al., "Quantization and Training of Neural Networks for Efficient
  Integer-Arithmetic-Only Inference", *CVPR*, 2018.
- R. A. DeMillo, R. J. Lipton, F. G. Sayward, "Hints on Test Data Selection: Help for the
  Practicing Programmer", *IEEE Computer*, vol. 11, no. 4, 1978.
- A. Piziali, *Functional Verification Coverage Measurement and Analysis*, Springer, 2004.
- C. Spear, G. Tumbush, *SystemVerilog for Verification*, 3rd ed., Springer, 2012.
- IEEE Std 1800-2017, *SystemVerilog*, clause 19 (functional coverage).
