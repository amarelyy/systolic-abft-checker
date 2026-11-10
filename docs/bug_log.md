# Bug log

One entry per bug, written as soon as it is fixed.

| # | Date | Symptom | Root cause | Fix | Log |
|---|---|---|---|---|---|
| 1 | 2026-11-10 | Random test: every multiply reported latency 1 cycle longer than expected, even with 0 stalls. C was correct. | Testbench. The monitor counts the clock edge that accepts `start`; the scoreboard formula (4N - 1) did not. The RTL was right. | Scoreboard expects 4N edges, counting the accepting edge. | `logs/2026-11-10T185054_random_W18/` |
| 2 | 2026-11-10 | Random test with 50 multiplies never finished. | Testbench. The monitor was started after the driver had already sent the first multiply, so it missed it, and the test waited forever for the 50th result. | Start the monitor before reset is released. The final wait is now bounded and fails with "monitor saw X of Y" instead of hanging. | `logs/2026-11-10T185054_random_W18/` |
