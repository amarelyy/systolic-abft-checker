# IC-B v2: Fault-Tolerant 4x4 INT8 Systolic Array

Build a small INT8 matrix-multiply accelerator (a 4x4 systolic array), add a checksum-based mechanism (ABFT) that detects hardware errors at runtime, and measure how well that mechanism works and what it costs.

## Status

Work in progress. Done and tested so far:

- 4x4 INT8 systolic array in two versions, weight-stationary and output-stationary, with
  control logic, back-pressure and a parameterized accumulator width (tested at 18, 16, 32).
- Python reference model, constrained-random and directed tests, functional coverage, and
  mutation tests of the testbench itself.
- Comparison of the two dataflows, including weight reuse and overlapped tiles.

Results and analysis: [docs/results.md](docs/results.md).

Still to come: the checksum-based error detector (ABFT), fault injection, formal proofs, and
synthesis area and timing results. The full README (question, method, results, limits) will be
added later.

## Setup

See [docs/tools.md](docs/tools.md).

## Run the tests

```bash
source env.sh      # every new terminal
pytest             # all tests, both designs, W = 18, 16, 32
```

Each simulation run saves its log, seed and tool versions to its own folder in `logs/`.
