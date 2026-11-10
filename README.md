# IC-B v2: Fault-Tolerant 4x4 INT8 Systolic Array

Build a small INT8 matrix-multiply accelerator (a 4x4 systolic array), add a checksum-based mechanism (ABFT) that detects hardware errors at runtime, and measure how well that mechanism works and what it costs.

Placeholder. The full README (question, method, results, limits) is written in step 5.9.

## Setup

See [docs/tools.md](docs/tools.md).

## Run the tests

```bash
source env.sh      # every new terminal
pytest             # all tests, W = 20, 24, 32
```

Each simulation run saves its log, seed and tool versions to its own folder in `logs/`.
