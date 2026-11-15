# Results

Every number in this file names the log folder it came from (all in `logs/`). Seed 12345
unless stated otherwise. Tool versions are in [tools.md](tools.md). The story of how each result came about, and
why, is in [story/README.md](story/README.md). Log paths below point to the newest run of each
kind (the `2026-11-15T1143xx` and `2026-11-15T1144xx` folders); older runs with the same seed
gave identical coverage and table files for the ones compared.

## Contents

1. [Summary](#1-summary)
2. [How to reproduce](#2-how-to-reproduce)
3. [Correctness: random and directed tests](#3-correctness-random-and-directed-tests)
4. [Can the testbench fail? Mutation tests](#4-can-the-testbench-fail-mutation-tests)
5. [Accumulator width: 18, 16, 32](#5-accumulator-width-18-16-32)
6. [Weight-stationary vs output-stationary](#6-weight-stationary-vs-output-stationary)
7. [ABFT checksums: Python prototype and hardware](#7-abft-checksums-python-prototype-and-hardware)
8. [Not measured yet](#8-not-measured-yet)
9. [Limits](#9-limits)
10. [References](#10-references)

---

## 1. Summary

**What exists:** a 4x4 INT8 systolic array in two versions, weight-stationary (WS) and
output-stationary (OS), each with control logic, back-pressure (stall), and a parameterized
accumulator width W. They are checked against a Python reference model.

**Findings so far**

| # | Finding | Evidence |
|---|---|---|
| 1 | Both designs are bit-exact with the reference model at W = 18, 16 and 32: 2000 random multiplies each with random stalls, 0 mismatches. | section 3 |
| 2 | Reachable functional coverage is 100% in all six runs. Unreachable bins are excluded with a written reason. | section 3 |
| 3 | The testbench catches 6 of 7 deliberately planted bugs. The seventh is a bug that changes nothing (an unneeded hardware step), and removing that step passed every test. | section 4 |
| 4 | No result of a 4x4 INT8 multiply can overflow at W = 18, so 18 is the smallest safe width. W = 16 is the only tested width where results wrap (2.3% of elements), and the arrays handle it correctly. | section 5 |
| 5 | For one tile OS is faster (11 vs 16 cycles). With weight reuse WS moves up to 33% less data. With overlapped tiles WS reaches 4 cycles per tile against 11 for OS, so WS is about 2.75 times faster in steady state. | section 6 |
| 6 | The checksum math works in Python: 0 false alarms in 100,000 fault-free matrix pairs at every width, including 12,677 that really overflow at W = 16. A reference that saturates instead of wrapping gives a false alarm on every overflowing matrix. | section 7 |
| 7 | In the Python model, the checksums detect every single, double and triple output error, and every datapath fault modelled (0 missed of 8,331,119 changed outputs). Four errors in a rectangle can cancel and are never detected. | section 7 |
| 8 | The checker hardware agrees with the Python model: 0 false alarms in 60,000 fault-free multiplies (4,362 of them really overflow at W = 16), every single wrong element planted in C is detected and located exactly, and the error flag appears 1 cycle after the result. The wrong values were added to C after the array, not injected inside it. | section 7.5 |

**Not measured yet:** fault injection inside the real array, formal proofs, real synthesis area
and timing. See [section 8](#8-not-measured-yet).

---

## 2. How to reproduce

```bash
source env.sh          # every new terminal
pytest                 # 42 tests: all designs and widths, about one minute
```

Each run writes its own folder in `logs/` with the simulator log, the seed, the tool versions
and (for random runs) `coverage.txt`. Single files: `pytest tb/test_random.py`,
`pytest tb/test_reuse.py`, `pytest tb/test_overlap.py`, `pytest tb/test_abft_model.py`, `pytest tb/test_abft_hw.py`. The checksum study is
`python model/abft_study.py`. `NUM_TESTS=50` shortens the random run.

---

## 3. Correctness: random and directed tests

### Setup

- **Designs under test:** `systolic_ws_ctrl` and `systolic_os_ctrl`, W = 18, 16 and 32.
- **Stimulus** (`tb/driver.py`): 2000 multiplies per run. Each matrix is one of three kinds:
  uniform (80%), extreme (every element -128 or 127, 10%), sparse (about 70% zeros, 10%).
  In the uniform kind, 20% of elements come from a corner list (-128, -127, -1, 0, 1, 126,
  127) and the rest are uniform over -128..127.
- **Back-pressure** (`StallDriver`): for each multiply one stall mode is picked: none,
  random (stall with probability 0.25 each cycle), or burst (bursts of 1 to 8 cycles). While
  `stall` is high, every register of the design holds its value.
- **Checking** (`tb/monitor.py`, `tb/scoreboard.py`): the monitor only watches the pins of
  the design. The scoreboard checks each C against `model/golden.py` bit for bit, and checks
  the latency. After start is accepted the driver puts random garbage on the input buses,
  to check that the design latched its inputs.
- **Directed tests** (`tb/test_directed.py`): identity matrix, all zeros, all -128 and 127
  combinations, a checkerboard of extremes, and mixed signs.
- **Coverage** (`tb/func_coverage.py`): 10 coverpoints; the total is their plain average,
  which is how SystemVerilog covergroups combine coverpoints by default (IEEE 1800-2017,
  clause 19).

### Results

| Design | W | Random multiplies | Mismatches | Coverage | Raw coverage | Log |
|---|---|---|---|---|---|---|
| WS | 18 | 2000 | 0 | 100.0% | 90.0% | `2026-11-15T114401_random_ws_W18` |
| WS | 16 | 2000 | 0 | 100.0% | 100.0% | `2026-11-15T114403_random_ws_W16` |
| WS | 32 | 2000 | 0 | 100.0% | 90.0% | `2026-11-15T114405_random_ws_W32` |
| OS | 18 | 2000 | 0 | 100.0% | 85.0% | `2026-11-15T114407_random_os_W18` |
| OS | 16 | 2000 | 0 | 100.0% | 95.0% | `2026-11-15T114408_random_os_W16` |
| OS | 32 | 2000 | 0 | 100.0% | 85.0% | `2026-11-15T114410_random_os_W32` |

The directed tests also pass for both designs (3 of 3 each, W = 18:
`2026-11-15T114321_directed_ws_W18`, `2026-11-15T114332_directed_os_W18`).

**Coverage vs raw coverage.** "Coverage" leaves out bins that no input can ever hit; "raw"
counts every bin. Each excluded bin is listed with its reason in `coverage.txt` of the run.
Two kinds are excluded:

- **"A result overflows"** at W = 18 and 32. The largest result of a 4x4 INT8 multiply is
  4 x 16384 = 65536 and the smallest is -65024. An 18-bit signed register holds
  -131072 .. 131071, so no result overflows. At W = 16 the register holds only
  -32768 .. 32767, the bins are reachable and were hit, so nothing is excluded there.
- **"Stalled during the load phase"** for OS, which has no load phase.

Coverage literature says unreachable bins should be excluded with a written reason, not
"closed" with more random tests (Piziali, 2004); SystemVerilog has `ignore_bins` for this.

### Why the designs pass with stalls

The stall is one clock enable that freezes every register at once: all PEs, the counter and
the output capture. A systolic array works because all cells move in lock-step with one clock
(Kung, 1982), and the input skew only sets the *relative* timing between cells. If every cell
skips the same cycle, the relative timing does not change, so a stalled cycle behaves like a
cycle that never happened. That is why C is correct for any stall pattern and the latency grows
by exactly one cycle per stall. The cost is one enable signal driving every register (a very
high fanout net). That is fine for 4x4; larger arrays usually use local handshakes.

### Why the stimulus is shaped

With plain uniform input every value has probability 1/256, so zeros and exact corner values
are rare. In the first WS W = 18 run (`logs/2026-11-10T190319_random_W18`), the "zero" sign bin
got 12,740 of 128,000 multiplied (A, B) pairs (about 10%; 128,000 = 2000 multiplies x 64 products) against about 0.4% for pure uniform input. This is the
usual argument for constrained-random over pure random stimulus (Spear and Tumbush, 2012).
For the 256 values of each value coverpoint, the coupon-collector estimate is about
256 x H(256) = 1,570 random draws, around 100 matrices, so 2000 multiplies is about 20 times
what is needed. In the same run the stall bins were uneven (none 735, load only 171, run only
511, load and run 583), as expected: the load phase lasts 4 cycles and the run phase 11, so a
random stall mostly lands in the run phase.

### Bugs found while building the testbench

Two, both in the testbench and not in the RTL: an off-by-one in the expected latency and a
monitor that started too late. See [bug_log.md](bug_log.md).

---

## 4. Can the testbench fail? Mutation tests

A testbench that always passes proves nothing unless it can also fail. Following mutation
testing (DeMillo, Lipton and Sayward, 1978), a bug is planted in a copy of the RTL and the
random test is run on it. All logs are in `logs/*_mutant_*` (run on 2026-11-10, 300 multiplies
each, W = 18). The mutated RTL copies were kept in a temporary folder (see `rtl_dir` in each
`run_info.txt`) and are not in the repo, so these seven runs cannot be re-created from the repo
today; only their logs survive. An early version of the m3 mutant was built wrongly and rebuilt;
the log shown is of the final one. Why each result came out as it did: [story chapter 9](story/03-story.md#chapter-9-mutation-tests-of-the-testbench).

| Design | Mutant | Planted bug | Caught? | How |
|---|---|---|---|---|
| WS | m1 | PEs ignore stall | yes, 165 of 300 | wrong C |
| WS | m2 | counter keeps running in the run phase while stalled | yes, 172 of 300 | wrong C |
| WS | m3 | start accepted while stalled | yes | monitor saw 270 of 300 multiplies |
| WS | m4 | skew feeds the wrong column of A | yes, 300 of 300 | wrong C |
| WS | m5 | array reads the input bus, not the latched copy | yes, 300 of 300 | wrong C |
| OS | a | skew feeds the wrong column of A | yes, 300 of 300 | wrong C |
| OS | b | the clear no longer zeroes the pass-through registers | **no, 0 of 300** | n/a |

- m1 and m2 are caught in about 55% of multiplies. That matches the share of multiplies that
  were stalled during the run phase: 1094 of 2000 (55%) in the first run. A multiply that is
  never stalled cannot show these bugs.
- m3 is not seen as a wrong value but as missing multiplies. Protocol checks catch bugs that
  comparing answers misses.
- **OS mutant b is a bug that changes nothing.** At the end of every multiply the skewed
  schedule has already pushed zeros through every pass-through register, so clearing them is
  unneeded. This was first only an argument from reading the schedule. To test it, the clear of
  those registers was **removed from the RTL** (`rtl/pe_os.sv`), and the whole suite was rerun
  (2000 random multiplies per width, with random stalls, back-to-back): 0 mismatches, in the
  logs of section 3 (the OS rows were produced after the removal). So the clear was unneeded,
  and the design should be a few multiplexers per PE smaller (area was not measured). Only the
  accumulator is cleared now.
  This is a test result, not a formal proof.

---

## 5. Accumulator width: 18, 16, 32

W = 18 is the main design. W = 16 and 32 are an ablation (a controlled comparison where one
setting changes): 16 is the only width where results can wrap, 32 is what real accelerators use.

**Why 18.** One output is a sum of K = 4 products of two INT8 numbers. A sum of K such
products needs about 16 + log2(K) bits, so 18. Real accelerators use 32 bits because their
dot products are much longer (K in the hundreds or thousands; TPU, Jouppi et al., 2017;
integer-only inference, Jacob et al., 2018). That reason does not apply to a single 4x4 array.

**Pre-study** (not final results: area is from generic gates).

| W | elements that overflow (1,000,000 random pairs) | cells | flip-flops |
|---|---|---|---|
| 16 | 0.30% | 8280 | 480 |
| 17 | 0% | 8617 | 492 |
| 18 | 0% | 8794 | 500 |
| 20 | 0% | 9042 | 508 |
| 24 | 0% | 9240 | 524 |
| 32 | 0% | 9430 | 556 |

Logs: `logs/2026-11-10T182224_overflow_study/`, `logs/2026-11-10T182225_area_sweep/`.
From W = 16 to 32 the area grows only about 14%, because psum starts at 0 and the top bits are
always copies of the sign, which Yosys merges. In a design where psum continues from an earlier
value those bits would really change and cost real area.

**Simulation at all three widths** (section 3 logs):

- **Wrap-around works.** At W = 16, 742 of 32,000 result elements (WS) and 827 (OS) overflowed
  in the random run, and all were bit-exact with the reference model, which wraps mod 2^W. This
  is the first test of wrap-around in the full array, and it is the case the checksum has to
  survive later.
- **The stimulus shaping matters.** Pure uniform input overflowed 0.30% of elements at W = 16;
  the shaped stimulus gives 2.3% for WS (742 of 32,000) and 2.6% for OS (827 of 32,000), about 8 times more.
- **W = 18 and 32 behave identically in simulation.** With no overflow possible, the extra bits
  of W = 32 are copies of the sign. Differences can only show up in area and in fault
  injection, where flips of those bits are expected to be mostly masked. This will be measured
  later.

---

## 6. Weight-stationary vs output-stationary

In **WS** each PE keeps one weight and the activations flow past, so the weights have to be
loaded first (4 cycles). In **OS** each PE keeps its own result and both inputs flow past, so
there is no load phase.

### 6.1 One tile

| | WS | OS | Source |
|---|---|---|---|
| Edges from accepting start to done (accepting edge counted) | 16 | 11 | measured; checked on all 2000 multiplies of each run. notes.md counts the cycles after the accepting edge, which is 15 and 10 |
| Phases | 4 load, 11 run, 1 done | 10 run, 1 done | RTL |
| PE utilisation (64 multiply-adds / (16 PEs x cycles)) | 25.0% | 36.4% | computed from the measured cycles |
| Extra register per PE | 8-bit stored weight | none | RTL |

### 6.2 Weight reuse: one B for T tiles of A (no overlap)

Test `tb/test_reuse.py`, W = 18, logs `2026-11-15T114412_reuse_ws_W18` and
`2026-11-15T114412_reuse_os_W18` (file `reuse.txt` in each). WS loads B once and skips the load
for the other tiles (the B given on those tiles is random garbage, and every result still
matches the reference, so the weights really are reused). OS streams B again for every tile.
"Moved" counts INT8 elements that crossed the array boundary, read from counters inside the RTL.

| T tiles | WS cycles | OS cycles | WS elements moved | OS elements moved | WS moves |
|---|---|---|---|---|---|
| 1 | 16 | 11 | 48 | 48 | same |
| 2 | 28 | 22 | 80 | 96 | 17% less |
| 4 | 52 | 44 | 144 | 192 | 25% less |
| 8 | 100 | 88 | 272 | 384 | 29% less |
| 16 | 196 | 176 | 528 | 768 | 31% less |

The measurements fit exact formulas: WS cycles = 12T + 4 and OS cycles = 11T; WS elements =
16 + 32T and OS elements = 48T. As T grows, WS moves 2/3 of the OS traffic (33% less).

With tiles run one after another, **OS is still faster in cycles** (176 vs 196 at T = 16). A WS
tile with weights already loaded takes 12 cycles against 11 for OS, because its result also has
to travel down to the bottom row, one cycle more than OS needs to finish accumulating.

### 6.3 Overlapping tiles (ablation)

The tiles above run strictly one after another. A systolic array can instead start the next
tile while the previous one is still draining. This ablation turns the overlap on step by step.
Test `tb/test_overlap.py` drives the bare WS array (`systolic_ws`, no control logic) with 8
tiles that share one B, weights loaded once. Tile m starts II cycles after tile m-1, where II is
the initiation interval. Every result is checked against the reference model.
Logs: `2026-11-15T114341_overlap_W18` (also W = 16 and 32, with identical numbers).

| II (cycles between tile starts) | Total cycles for 8 tiles | Cycles per tile | PE utilisation | Tiles correct | Meaning |
|---|---|---|---|---|---|
| 11 | 92 | 11.50 | 36.4% | 8 of 8 | no overlap |
| 8 | 71 | 8.88 | 50.0% | 8 of 8 | |
| 6 | 57 | 7.12 | 66.7% | 8 of 8 | |
| 5 | 50 | 6.25 | 80.0% | 8 of 8 | |
| **4** | **43** | **5.38** | **100.0%** | **8 of 8** | **full overlap** |
| 3 | 36 | 4.50 | not meaningful | 1 of 8 | two tiles want the same input lane |

Total cycles = 4 (weight load) + 7 x II + 11. Cycles per tile include the one-time load and
drain, so they tend to II as T grows; the steady-state rate is II.

- **The limit is II = N = 4.** Row k of the array is busy with one tile for exactly N cycles, so
  the next tile can use row k right after. Below that, two tiles need the same row in the same
  cycle, and the test confirms the results break (only 1 of 8 correct). At II = 4 every PE does
  a multiply-add every cycle, which is 100% utilisation.
- **Steady state: WS 4 cycles per tile, WS without overlap 12, OS 11.** For 8 tiles that is 43
  cycles against 100 (WS, no overlap) and 88 (OS), so overlapped WS is about 2 times faster
  than OS at 8 tiles and approaches 2.75 times (11 / 4) as T grows.
- **This changes the conclusion of 6.2.** The earlier result, "OS is faster", was a property of
  running tiles one after another, not of the dataflow. Once weights are reused *and* tiles
  overlap, WS wins on both speed and memory traffic. This matches why WS exists in the
  literature (Chen, Emer and Sze, 2016).

**Caveats:**

- The overlap is driven by the testbench on the bare array. `systolic_ws_ctrl` does not
  implement it yet, and stalls during overlap were not tested.
- OS was not tested with overlap. With its single clear signal it probably cannot overlap
  without a clear that is staggered per PE, but this is untested.
- The comparison is for one B and ideal back-to-back tiles. For a single tile OS is faster.

---

## 7. ABFT checksums: Python prototype and hardware

Before building any checker hardware, the checksum math was written and tested in Python
(`model/abft.py`). This model is also what the hardware checker will be compared against.

### 7.1 How the checksums work

For C = A x B, the sum of each column of C equals (the column sums of A) times B, and the sum
of each row of C equals A times (the row sums of B). Example from the project plan:
A = [[1,2],[3,4]], B = [[5,6],[7,8]], C = [[19,22],[43,50]]. Column sums of C are [62, 72]; column
sums of A are [4, 6], and [4, 6] x B = [62, 72]. They match. If one element of C is wrong, exactly
one column sum and one row sum disagree, and where they cross is the wrong element.
This is algorithm-based fault tolerance (Huang and Abraham, 1984): the extra work is two small
vector-matrix products instead of a second copy of the whole array.

The identity is linear, so it also holds modulo 2^W. If the output wraps around, the checksums
wrap the same way and still match, as long as the reference wraps exactly like the hardware.

### 7.2 Results

Log: `logs/2026-11-15T114228_abft_prototype/summary.txt` (`python model/abft_study.py`, seed
12345). Pass/fail tests of the same properties: `tb/test_abft_model.py` (10 tests, all pass).

**Without wrap-around:** the column and row identities hold for all 100 random matrix pairs.

**With wrap-around, no fault injected** (100,000 random pairs per width, shaped stimulus):

| W | matrices that really overflow | false alarms |
|---|---|---|
| 16 | 12,677 | **0** |
| 17 | 887 | **0** |
| 18 | 0 | **0** |
| 32 | 0 | **0** |

**Wrong reference (saturating instead of wrapping)**, same inputs:

| W | matrices that really overflow | false alarms |
|---|---|---|
| 16 | 12,677 | 12,677 |
| 17 | 887 | 887 |

Every overflowing matrix raised a false alarm, and none of the others did.

**Abstract errors put into C** (W = 18, 20,000 pairs per row):

| Error pattern | Changed | Detected | Missed |
|---|---|---|---|
| one element, one random bit flipped | 20,000 | 20,000 | 0 |
| two elements, one bit flipped in each | 20,000 | 20,000 | 0 |
| three elements, one bit flipped in each | 20,000 | 20,000 | 0 |
| four errors +d, -d, -d, +d at the corners of a rectangle | 20,000 | 0 | 20,000 |

The test `test_single_error_detected_and_located` also checks every position and every bit
flip of several matrices at W = 16 and 18: the flagged row and column are always the right ones.

**Datapath faults at the value level** (W = 18, 20,000 pairs per fault position). These are
modelled by the values they corrupt, not cycle by cycle, so they are a prediction and not a
hardware result:

| Fault | Fault positions | Changed outputs | Detected | Missed |
|---|---|---|---|---|
| one activation with one bit flipped (affects one row) | 128 | 2,446,608 | 2,446,608 | 0 |
| a bit stuck in the activation-passing register (many rows) | 192 | 3,383,711 | 3,383,711 | 0 |
| a bit stuck in a stored weight (one column) | 256 | 2,500,800 | 2,500,800 | 0 |

### 7.3 Why these results

- **No false alarms under wrap-around.** Both sides of the check are the same linear sum, taken
  mod 2^W. Wrapping removes a multiple of 2^W from a result and from the checksum equally, so
  nothing changes. This is why overflow alone must not raise an error, and the test at W = 16,
  with 12,677 really overflowing matrices, shows it on real overflow.
- **A saturating reference breaks it.** Saturation changes a result by an amount that is not a
  multiple of 2^W, so the sums disagree. This is the first pitfall in the project plan: a false
  alarm usually means the reference does not wrap like the hardware, not that the checker is
  wrong. The 12,677 of 12,677 shows it clearly.
- **Single, double and triple errors are always caught.** An error pattern escapes only if
  every affected row sum and every affected column sum is unchanged. With one error in a row,
  that row's sum changes by a nonzero amount (smaller than 2^W, so it cannot wrap to zero),
  so it is caught. Two or three errors can cancel inside one row or one column but not in
  both at once, because that needs every affected row and column to contain at least two
  errors. The smallest such pattern has four errors at the corners of a rectangle, and the
  last row of the table shows it going completely undetected. This is the known limit of row
  and column checksums (Huang and Abraham, 1984).
- **The datapath faults are caught because they stay inside one row or one column.** A
  corrupted activation only changes outputs of one row, and a corrupted weight only outputs of
  one column. Every column (or every row) then holds at most one wrong value, which the
  checksum sees. The stuck bit in the activation-passing register is the interesting case,
  because it corrupts several rows at once. It is still always caught: for a fixed stuck value,
  every error has the same sign (+2^b or -2^b), so the errors in a column cannot cancel each
  other. This corrects an earlier guess that such faults might rarely escape; the
  data say they cannot, and the argument says why.

### 7.4 What this predicts for the hardware, and what it does not cover

- **Prediction:** for a single fault inside the array that changes the output, detection
  coverage should be 100%. If fault injection into the real design gives less, the cause is
  something this model leaves out, and that is worth finding.
- **Not covered by this model:** faults in the control logic or the checker itself, several
  faults in one run, faults that corrupt the inputs A or B *before* the checker takes its
  copy (the checker would use the same wrong input, so it cannot see it), timing effects, and
  stuck-at faults in a limited window of cycles. Four simultaneous errors in a rectangle are
  possible in principle but would need a very specific multi-fault.
- **Hardware size hint:** the column sums of A are sums of four INT8 values, so they need 10
  bits (-512 to 508), not 8, in the reference path of the checker.

### 7.5 The checker in hardware

Design: `rtl/abft_checker.sv` and `rtl/top.sv` (one top for both dataflows, parameter `DATAFLOW`).
The checker keeps its own copy of A and B, computes the reference checksums over 4 cycles with a
small multiply-accumulate unit (8 multipliers), sums the rows and columns of C when `done` is
high, and reports one cycle later. Tests: `tb/test_abft_hw.py` (4 tests x 2 dataflows x 3
widths). The wrong value is added to C by a simulation-only variable in `top.sv`, **after** the
array, so these are faults at the output, not faults inside the array.

Logs: `logs/2026-11-15T1157xx_abft_hw_<ws|os>_W<18|16|32>/checker.txt`, seed 12345.

| Design | W | Fault-free multiplies | really overflow | False alarms | Single errors detected / located |
|---|---|---|---|---|---|
| WS | 18 | 10,000 | 0 | **0** | 864 / 864 |
| WS | 16 | 10,000 | 2,165 | **0** | 768 / 768 |
| WS | 32 | 10,000 | 0 | **0** | 1,536 / 1,536 |
| OS | 18 | 10,000 | 0 | **0** | 864 / 864 |
| OS | 16 | 10,000 | 2,197 | **0** | 768 / 768 |
| OS | 32 | 10,000 | 0 | **0** | 1,536 / 1,536 |

- **Multiple errors** (300 patterns each, identical in all six runs): 2, 3, 4, 5 and 6 random
  wrong elements detected 300 of 300; the cancelling rectangle (+d, -d, -d, +d) detected 0 of 300.
  The hardware agreed with `model/abft.py` in every single case.
- **Latency:** the error flag is visible exactly 1 cycle after `done` in all 60,000 multiplies.
- **Weight reuse** (WS): 14 multiplies per run with garbage on the B bus after the first tile,
  0 false alarms.
- **Assertion** that the reference is ready before the result: never fired.

**The first run failed.** All four tests failed: every multiply raised a false alarm, and no
error was located (`logs/2026-11-15T115400_abft_hw_ws_W18`, kept). Cause: in SystemVerilog an
element taken from a packed array is unsigned even if the array is declared signed, so negative
INT8 values were added as large positive numbers in the reference sums. The Python model does not
have this problem, which is why the model was a useful answer key. Fix: `$signed()` on every use.
See [bug_log.md](bug_log.md).

**Can the tests fail?** Four planted bugs in the checker (`logs/*_mutant_chk_*`, 300 multiplies,
W = 18, WS): row checks ignored, `keep_w` ignored, reference stops one cycle early, row
comparison skips the top bit. All four were caught.

**Why these results.** The checker does the same linear sums as the model, so it agrees with it
and survives wrap-around (section 7.3). The rectangle cancels all its row and column sums, so it
is never seen. The 1-cycle delay is the register that holds the result.

**What this does not show.** No fault has been injected inside the array. The Python prediction of
100% detection for faults inside the array (section 7.4) is therefore still a prediction, and
masked faults, the effect of width on them, and the area and speed cost are not measured yet.

## 8. Not measured yet

See also the plain-English view of what is solid and what is risky in
[story/02-how-is-it-looking.md](story/02-how-is-it-looking.md).

- Faults injected *inside* the array (not only added to the finished result C), tested against
  the checker hardware.
- Fault injection (bit-flip and stuck-at) into the real design: detection coverage, masked
  faults and latency per width. The Python prediction above is the number to compare with.
- Formal proofs (SymbiYosys) of the processing-element behaviour and the handshake.
- Synthesis area and timing with and without the checker, from a real cell library.

## 9. Limits

- Verilator is 2-state (no X values), so a bug that only shows as an X, for example a register
  without reset, cannot be seen. Every register in the RTL has a synchronous reset.
- The mutation tests use 11 hand-picked bugs (7 on the arrays, 4 on the checker). They show the testbench catches those kinds of
  bugs, not all. An automatic mutation tool (MCY, in the OSS CAD Suite) would give a fuller
  picture.
- Coverage is sampled at the transaction level (the A, B and C the monitor saw), not inside
  each PE.
- Area numbers so far are from generic gates, not a real cell library.
- The ABFT hardware results in section 7.5 add wrong values to C after the array. Faults inside
  the array have not been injected yet.
- Only seed 12345 was used for the results above; other seeds were not run.
- The width ablation at W = 32 will contain register bits that synthesis removes (sign copies);
  fault-injection results there must separate real bits from these ghost bits (not measured yet).

## 10. References

- H. T. Kung, "Why systolic architectures?", *IEEE Computer*, vol. 15, no. 1, 1982.
- N. P. Jouppi et al., "In-Datacenter Performance Analysis of a Tensor Processing Unit",
  *ISCA*, 2017.
- B. Jacob et al., "Quantization and Training of Neural Networks for Efficient
  Integer-Arithmetic-Only Inference", *CVPR*, 2018.
- Y.-H. Chen, J. Emer, V. Sze, "Eyeriss: A Spatial Architecture for Energy-Efficient Dataflow
  for Convolutional Neural Networks", *ISCA*, 2016.
- R. A. DeMillo, R. J. Lipton, F. G. Sayward, "Hints on Test Data Selection: Help for the
  Practicing Programmer", *IEEE Computer*, vol. 11, no. 4, 1978.
- A. Piziali, *Functional Verification Coverage Measurement and Analysis*, Springer, 2004.
- C. Spear, G. Tumbush, *SystemVerilog for Verification*, 3rd ed., Springer, 2012.
- IEEE Std 1800-2017, *SystemVerilog*, clause 19 (functional coverage).
- K.-H. Huang, J. A. Abraham, "Algorithm-Based Fault Tolerance for Matrix Operations",
  *IEEE Transactions on Computers*, vol. C-33, no. 6, 1984.
