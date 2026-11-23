# IC-B v2: Fault-Tolerant 4x4 INT8 Systolic Array

Build a small INT8 matrix-multiply accelerator (a 4x4 systolic array), add a checksum-based mechanism (ABFT) that detects hardware errors at runtime, and measure how well that mechanism works and what it costs.

## Status

Work in progress. Done and tested so far:

- 4x4 INT8 systolic array in two dataflows, weight-stationary and output-stationary, with control logic,
  back-pressure and a parameterized accumulator width (tested at 18, 16 and 32 bits).
- Checksum-based error checker (ABFT) with its own copies of the inputs; it locates a single wrong
  element by row and column.
- Python reference model, constrained-random and directed tests with functional coverage, and mutation
  tests of the testbench itself.
- Fault injection into the registers of the array, the control logic and the checker, with two random
  seeds. Formal proofs with SymbiYosys and a Lean proof of the checker arithmetic.

Still to come: synthesis area and timing with and without the checker, and the full README (question,
method, results, limits).

## Setup

Needs the OSS CAD Suite (Verilator, Yosys, SymbiYosys, GTKWave) and a Python virtual environment with
cocotb, pytest and numpy; the formal proofs also use Lean 4 (installed with elan).

| Tool | Version used |
|---|---|
| OSS CAD Suite build | 2026-11-10 |
| Verilator | 5.055 |
| Yosys | 0.70+368 |
| cocotb, pytest, numpy | 2.1.0, 9.2.0, 2.2.6 (see `requirements.txt`) |
| Lean 4 | v4.35.0 |

`source env.sh` puts the tools on the PATH (edit the path of the OSS CAD Suite there if needed).

## Run the tests

```bash
source env.sh      # every new terminal
pytest             # all tests, both designs, W = 18, 16, 32
```

Each simulation run saves its log, seed and tool versions to its own folder in `logs/`.

### Run in Docker (reproducible on Windows or macOS)

The project runs natively on Ubuntu with `source env.sh`. The `Dockerfile` builds the same environment
(Ubuntu 24.04, OSS CAD Suite 2026-11-10, Lean v4.35.0, the pinned Python packages) for other systems:

```bash
docker build -t systolic-abft .
docker run --rm -v "$PWD/logs:/work/logs" systolic-abft                    # pytest (all 66 tests, about 7 min)
docker run --rm -v "$PWD/logs:/work/logs" systolic-abft formal/run_all.sh  # formal proofs
docker run --rm -v "$PWD/logs:/work/logs" systolic-abft lean/check.sh      # Lean proof
```

The `-v` option keeps the run logs on your machine. `.gitattributes` keeps shell scripts on LF line
endings so they also work after a Windows checkout.

Formal proofs: `formal/run_all.sh`. Lean proof: `lean/check.sh`. Results of every run are saved in `logs/`
and the fault-injection tables in `results/`.
