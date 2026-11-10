# Tools and versions (step 1.1)

Recorded on 2026-11-10. A result is only reproducible if these versions are known.
If a tool is updated, add a new dated section below instead of editing this one.

## Machine

| Item | Value |
|---|---|
| OS | Ubuntu 22.04.5 LTS, x86_64 |
| C++ compiler (used by Verilator) | g++ 11.4.0 |
| make | GNU Make 4.3 |

## OSS CAD Suite

Build `oss-cad-suite-linux-x64-20261110`, from
https://github.com/YosysHQ/oss-cad-suite-build/releases/tag/2026-11-10 ,
installed in `~/tools/oss-cad-suite`.

| Tool | Version | Used for |
|---|---|---|
| Verilator (chosen simulator) | 5.055 devel rev v5.054-183-g9040f8666 | All simulation, SVA assertions |
| Icarus Verilog (backup only) | 14.0 (devel) s20260301-948-gbd5af2914 | Not used for results |
| Yosys | 0.70+368 (git sha1 7cf88aca6) | Synthesis, cell counts (steps 5.5, 5.6) |
| SymbiYosys (sby) | from the same suite build | Formal proofs (steps 5.2, 5.4) |
| Z3 | 4.15.5 | Formal solver |
| Bitwuzla | 0.9.1 | Formal solver |
| Boolector | 3.2.4 | Formal solver |
| Yices | 2.7.0 | Formal solver |
| GTKWave (chosen waveform viewer) | v4.0.0-prealpha (e40ba79) | Waveform debugging (steps 1.14, 3.9) |

## Python (project venv, `.venv/`)

Built from the system Python, because the suite's bundled Python cannot create a venv.
The suite also bundles a cocotb development build (2.1.0.dev0). It is not used, because a
stable release is easier to reproduce.

| Package | Version |
|---|---|
| Python | 3.10.12 |
| cocotb | 2.1.0 |
| pytest | 9.2.0 |
| numpy | 2.2.6 |

## Choices and why

- **Simulator: Verilator.** It runs SVA assertions (step 1.6), and it is fast enough for the
  10,000-run and 3 x 1000-injection campaigns. Verilator is 2-state (no X values), so every
  register in the RTL must have a reset.
- **Waveform viewer: GTKWave.** Surfer is in the suite but needs glibc 2.43, which Ubuntu
  22.04 does not have.
- **OpenLane / OpenSTA: not installed yet.** They are only needed at step 5.7. Record the
  version and PDK here when they are installed.
- **Old apt packages** (`/usr/bin/verilator` 4.038, `/usr/bin/yosys` 0.9,
  `/usr/bin/iverilog` 11.0) are still on the system. `source env.sh` puts the suite first on
  PATH, so they are not used. Do not run tests without sourcing `env.sh`.

## How to set up a terminal

```bash
source env.sh
```

This loads the suite and the venv, and removes snap GTK variables that break GTKWave when the
terminal is opened inside snap VS Code.

## How to reinstall from scratch

```bash
mkdir -p ~/tools && cd ~/tools
wget https://github.com/YosysHQ/oss-cad-suite-build/releases/download/2026-11-10/oss-cad-suite-linux-x64-20261110.tgz
tar -xzf oss-cad-suite-linux-x64-20261110.tgz
cd <repo>
/usr/bin/python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```
