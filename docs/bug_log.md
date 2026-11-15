# Bug log

One entry per bug, written as soon as it is fixed.

| # | Date | Symptom | Root cause | Fix | Log |
|---|---|---|---|---|---|
| 1 | 2026-11-10 | Random test: every multiply reported latency 1 cycle longer than expected, even with 0 stalls. C was correct. | Testbench. The monitor counts the clock edge that accepts `start`; the scoreboard formula (4N - 1) did not. The RTL was right. | Scoreboard expects 4N edges, counting the accepting edge. | `logs/2026-11-10T185054_random_W18/` |
| 2 | 2026-11-10 | Random test with 50 multiplies never finished. | Testbench. The monitor was started after the driver had already sent the first multiply, so it missed it, and the test waited forever for the 50th result. | Start the monitor before reset is released. The final wait is now bounded and fails with "monitor saw X of Y" instead of hanging. | `logs/2026-11-10T185054_random_W18/` |
| 3 | 2026-11-15 | Checker hardware: every fault-free multiply raised a false alarm (300 of 300), and all injected errors were detected but none located. | **RTL bug.** In SystemVerilog an element picked out of a packed array is unsigned even if the array is declared signed, so negative INT8 values were added as large positive numbers in the reference checksums. | `$signed()` on every use of an INT8 element in `rtl/abft_checker.sv`; signed arrays for the sums. | `logs/2026-11-15T115400_abft_hw_ws_W18` (failed run, kept) |
| 4 | 2026-11-15 | One assertion in the weight-reuse hardware test could never fail. | Testbench. It compared a value with itself (`x if False else c`). | Compare the array's real output with the golden model. | `tb/test_abft_hw.py` |
| 5 | 2026-11-15 | The first fault-injection run stopped after the first injected flip: `Assertion failed ... a_mac`, then `$stop`. | Flow, not design. The PE has a simulation-only assertion `psum_out == psum_in + a*w`, which a flipped `psum_out` breaks. Building without `--assert` did not switch it off, because Verilator 5 checks concurrent assertions anyway. | Macro `NO_RTL_ASSERT` that the three RTL files respect; injection runs are built with `assertions=False`, which defines it. | `logs/2026-11-15T121304_injection_ws_W18` |
