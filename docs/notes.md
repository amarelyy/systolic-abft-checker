# Notes

A long story-style explanation of the whole project is in [story/README.md](story/README.md).
This file keeps the data-flow walk-through and the accumulator-width decision.

## Data flow of one WS multiply

Source: `logs/2026-11-10T172359_ws_ctrl_W20_waves/` (`dump.vcd`, test `test_identity`,
W = 20, seed 12345; recorded before the width was fixed at 18, which does not change the
data flow). The table below is `cycle_table.txt` from that folder: signals of
`systolic_ws_ctrl` sampled once per cycle (on the falling clock edge), starting at the cycle
after `start`.

Open the waveform with:

```bash
source env.sh
gtkwave logs/2026-11-10T172359_ws_ctrl_W20_waves/dump.vcd
```

Inputs: B = identity, and A is

```
[[-8 -7 -6 -5]
 [-4 -3 -2 -1]
 [ 0  1  2  3]
 [ 4  5  6  7]]
```

```
cyc state cnt ld | w_top[0..3]      | a_left[0..3]     | psum_bottom[0..3]     | done
  0 LOAD    0  1 | [0, 0, 0, 1]     | [0, 0, 0, 0]     | [0, 0, 0, 0]          | 0
  1 LOAD    1  1 | [0, 0, 1, 0]     | [0, 0, 0, 0]     | [0, 0, 0, 0]          | 0
  2 LOAD    2  1 | [0, 1, 0, 0]     | [0, 0, 0, 0]     | [0, 0, 0, 0]          | 0
  3 LOAD    3  1 | [1, 0, 0, 0]     | [0, 0, 0, 0]     | [0, 0, 0, 0]          | 0
  4 RUN     0  0 | [0, 0, 0, 0]     | [-8, 0, 0, 0]    | [0, 0, 0, 0]          | 0
  5 RUN     1  0 | [0, 0, 0, 0]     | [-4, -7, 0, 0]   | [0, 0, 0, 0]          | 0
  6 RUN     2  0 | [0, 0, 0, 0]     | [0, -3, -6, 0]   | [0, 0, 0, 0]          | 0
  7 RUN     3  0 | [0, 0, 0, 0]     | [4, 1, -2, -5]   | [0, 0, 0, 0]          | 0
  8 RUN     4  0 | [0, 0, 0, 0]     | [0, 5, 2, -1]    | [-8, 0, 0, 0]         | 0
  9 RUN     5  0 | [0, 0, 0, 0]     | [0, 0, 6, 3]     | [-4, -7, 0, 0]        | 0
 10 RUN     6  0 | [0, 0, 0, 0]     | [0, 0, 0, 7]     | [0, -3, -6, 0]        | 0
 11 RUN     7  0 | [0, 0, 0, 0]     | [0, 0, 0, 0]     | [4, 1, -2, -5]        | 0
 12 RUN     8  0 | [0, 0, 0, 0]     | [0, 0, 0, 0]     | [0, 5, 2, -1]         | 0
 13 RUN     9  0 | [0, 0, 0, 0]     | [0, 0, 0, 0]     | [0, 0, 6, 3]          | 0
 14 RUN    10  0 | [0, 0, 0, 0]     | [0, 0, 0, 0]     | [0, 0, 0, 7]          | 0
 15 IDLE   10  0 | [0, 0, 0, 0]     | [0, 0, 0, 0]     | [0, 0, 0, 0]          | 1
```

What happens:

1. **LOAD, cycles 0-3.** One row of B goes into the top of the array per cycle, last row
   first (`w_top` = row 3, then 2, 1, 0 of the identity). Each cycle the weights shift down
   one PE, so after 4 cycles PE[k][j] holds B[k][j].
2. **RUN, feeding (t = 0-6).** Row k of the array gets A[t-k][k], so row k starts k cycles
   later than row 0. This is the skew: in each cycle the values form a diagonal wavefront.
   Example at t = 3: rows 0..3 get A[3][0]=4, A[2][1]=1, A[1][2]=-2, A[0][3]=-5.
3. **Inside the array.** Each value moves one PE right per cycle, and each partial sum moves
   one PE down per cycle. The skew makes A[i][k] meet the partial sum for C[i][j] exactly at
   PE[k][j], at cycle t = i + k + j.
4. **Output (t = 4-10).** C[i][j] leaves the bottom of column j at t = i + j + N. Column 0 is
   the first out (t = 4), and column j comes out j cycles later. Since B = identity, the
   outputs are the rows of A, skewed: C[0][0] = -8 at t = 4, C[3][3] = 7 at t = 10.
5. **done** is high in the cycle after the last capture. From the clock edge that takes
   `start` to the cycle where `done` is high is 4 (load) + 11 (run) = 15 cycles after that edge.
   Counting the accepting edge itself, as the scoreboard and `results.md` do, it is 16 edges.
   The tests check this number for every multiply. Inputs are latched at start, and
   `c_mat` holds the result until the next start.

Utilisation: each PE does useful work for 4 of the 11 RUN cycles. Running tiles back-to-back
removes most of this idle time: see the overlap ablation in `results.md`. A tile can start every
4 cycles, because row k of the array is busy with one tile for exactly 4 cycles.

## Accumulator width: W = 18

### Why 18

One output of a 4x4 INT8 multiply is a sum of K = 4 products. The largest result is
4 x (-128 x -128) = 65536 = 2^16, and the smallest is 4 x (-128 x 127) = -65024.
In general a sum of K products of two b-bit numbers needs about 2b + log2(K) bits, which
for b = 8 and K = 4 is 18 bits. A signed 18-bit register holds -131072 .. 131071, so
**W = 18 is the smallest width that can never overflow** for this array.

Real accelerators use 32-bit accumulators instead (for example the TPU, Jouppi et al.,
ISCA 2017, and the integer-only inference scheme of Jacob et al., CVPR 2018), because their
dot products are much longer (K in the hundreds or thousands, often summed over several
passes). That reason does not apply to a single 4x4 array, so this project uses the minimum.

### Consequence: overflow cannot happen in the array

With W = 18 no result can wrap, so:
- the coverage bin "a result overflows" can never be hit (see `docs/results.md`),
- overflow behaviour is still tested at the PE level: the PE random test feeds random
  W-bit `psum_in` values, so wrap-around of the adder is checked there.

### Pre-study used for the decision

These are not final results: area here is generic Yosys gates. Full synthesis results will
be added later.

How often a result overflows, for 1,000,000 random 4x4 INT8 matrix pairs (seed 12345).
Log: `logs/2026-11-10T182224_overflow_study/overflow_study.txt`
(`python model/overflow_study.py`).

| W | elements that overflow | matrices with at least one overflow | corner cases that overflow |
|---|---|---|---|
| 16 | 0.30% | 4.49% | all three (-128x-128, 127x127, -128x127) |
| 17 | 0% | 0% | only all -128 x all -128 (result 65536) |
| 18 | 0% | 0% | none |
| 20, 24, 32 | 0% | 0% | none |

Area of the array alone (no checker).
Log: `logs/2026-11-10T182225_area_sweep/summary.txt` (`synth/area_sweep.sh`).

| W | cells | flip-flops |
|---|---|---|
| 16 | 8280 | 480 |
| 17 | 8617 | 492 |
| 18 | 8794 | 500 |
| 20 | 9042 | 508 |
| 24 | 9240 | 524 |
| 32 | 9430 | 556 |

From W = 16 to 32 the cell count grows only about 14%. The reason: psum starts at 0, so the
bits above about bit 17 are always copies of the sign bit, and Yosys proves this and merges
many of those flip-flops. (Without merging the count is 16 x (8 + 8 + W) minus the 32 unused
`a_out` bits of the last column, which is 480 at W = 16 and matches exactly.) In a design
where psum continues from an earlier value, those bits would really change and would cost
real area.

A side effect for fault injection: at large W, many register bits in simulation do not
exist after synthesis. Faults injected into those bits test hardware that is not there.

## Output-stationary design, in short

`systolic_os_ctrl` has the same ports as `systolic_ws_ctrl`, so one testbench drives both. It uses its own PE file (`rtl/pe_os.sv`) because its PE keeps the
accumulator, while the weight-stationary PE keeps a weight: different registers, so they are not
the same PE.
There is no load phase. A[i][k] and B[k][j] meet in PE[i][j] at cycle t = i + j + k, and each
PE adds the product into its own accumulator. The accumulators are read directly as the result,
so `done` comes one cycle after the last multiply-add. A multiply takes 11 edges counting the accepting edge (WS: 16); 10 cycles after the
accepting edge (WS: 15).

The accumulator is cleared when `start` is accepted. The pass-through registers are not
cleared: by the end of a multiply the skewed schedule has already pushed zeros through all of
them (tested, see `results.md`, section 4).

## ABFT checker hardware, in short

`abft_checker` sits next to the array (`top.sv` joins them). When a multiply is accepted it copies
A and B, then in 4 cycles computes the reference checksums with 8 small multipliers: (column sums
of A) x B for the columns and A x (row sums of B) for the rows. When `done` is high it adds up the
rows and columns of C, compares, and one cycle later pulses `chk_valid` with `err_flag`,
`err_loc_valid` (exactly one row and one column disagree) and the row and column.

A trap worth remembering: in SystemVerilog a slice of a packed array is unsigned even if the array
is declared signed, so INT8 elements must go through `$signed()` (see `bug_log.md`, entry 3).

In simulation, `top.sv` adds the variable `inj_add` to C, so the testbench can plant a wrong value
after the array. Results are in `results.md`, section 7.5, and the story is in `story/03-story.md`,
chapter 17.

## Fault injection, in short

`tb/injector.py` reaches into the running design (`dut.g_ws.u_ctrl.u_array.g_row[k].g_col[j].u_pe`)
and changes a register from the testbench: a *flip* XORs one bit once at a chosen cycle, a *stuck*
fault forces one bit for a window of cycles. The multiply then finishes, and the classifier
compares the output with the golden model and the checker's flag: masked, detected or missed.
Cycle 0 is the first falling clock edge after the edge that accepted start. Targets are listed in
`tb/targets.py`. Per-injection CSV files are in `results/`; the story is chapter 18 of
`story/03-story.md` and the numbers are in `results.md`, section 7.6.

Two things worth remembering: injection runs are built without the RTL assertions (macro
`NO_RTL_ASSERT`), because a flipped register fires them; and the W = 16 and W = 32 runs use the
same random draws, so they are one sample seen twice.

## Formal proofs, in short

`formal/` has SymbiYosys files (`pe_props.sby`, `handshake.sby`, `checker_props.sby`) and wrapper
modules (`pe_formal.sv`, `pe_os_formal.sv`, `ctrl_formal.sv`, `checker_formal.sv`) that hold the
properties; the RTL is not touched. `formal/run_all.sh` runs everything that is expected to finish
and saves the result in `logs/`. The proof of the checker's arithmetic (`checker_algebra_attempt.sby`)
did not finish. Remember: Yosys cannot read the `assert property` blocks in the RTL, so formal runs
define `SYNTHESIS`; and the PE proofs are unbounded while the control proofs are bounded.

## Lean proof of the checker algebra, in short

`lean/AbftChecker.lean` models the checker's sums (one wrapped addition at a time, modulo m) and
proves, for every A, B and every m: no false alarm; a single wrong element gives exactly one wrong
column and one wrong row (its own); an error pattern inside one row or column is always detected;
and the checker's intermediate values fit their bit widths for INT8 inputs. Run `lean/check.sh` after
`source env.sh`. It is a proof of a model, not of the RTL. Lean is installed in `~/.elan`.

