"""Shared cocotb runner: builds with Verilator and saves every run to its own logs/ folder.

Each run gets logs/<timestamp>_<tag>/ with sim.log (includes the seed), build.log,
results.xml and run_info.txt (W, seed, tool versions). Logs are never deleted
(tab 5, filing rule 6).
"""

import datetime
import os
import subprocess
from pathlib import Path

from cocotb_tools.runner import get_results, get_runner

ROOT = Path(__file__).resolve().parent.parent
RTL = ROOT / "rtl"
DEFAULT_SEED = 12345


def _version(cmd):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return (out.stdout or out.stderr).splitlines()[0]
    except (OSError, IndexError):
        return "unknown"


def run_cocotb(toplevel, sources, test_module, tag, parameters=None, seed=None, waves=False,
               testcase=None):
    """Build and run one cocotb test module, and return the log folder."""
    parameters = parameters or {}
    seed = int(os.environ.get("SEED", seed if seed is not None else DEFAULT_SEED))
    stamp = datetime.datetime.now().strftime("%Y-%m-%dT%H%M%S")
    log_dir = ROOT / "logs" / f"{stamp}_{tag}"
    log_dir.mkdir(parents=True)

    param_str = "_".join(f"{k}{v}" for k, v in parameters.items())
    build_dir = ROOT / "sim_build" / f"{toplevel}_{param_str}"

    import cocotb
    (log_dir / "run_info.txt").write_text(
        f"toplevel: {toplevel}\n"
        f"test_module: {test_module}\n"
        f"parameters: {parameters}\n"
        f"seed: {seed}\n"
        f"verilator: {_version(['verilator', '--version'])}\n"
        f"cocotb: {cocotb.__version__}\n"
    )

    runner = get_runner("verilator")
    runner.build(
        sources=[RTL / s for s in sources],
        hdl_toplevel=toplevel,
        parameters=parameters,
        build_args=["--assert", "-Wall"],
        build_dir=build_dir,
        waves=waves,
        always=True,
        log_file=log_dir / "build.log",
    )
    runner.test(
        hdl_toplevel=toplevel,
        test_module=test_module,
        testcase=testcase,
        test_dir=log_dir,
        build_dir=build_dir,
        seed=seed,
        waves=waves,
        extra_env={"PYTHONPATH": f"{ROOT}:{ROOT / 'tb'}"},
        results_xml=str(log_dir / "results.xml"),
        log_file=log_dir / "sim.log",
    )
    num_tests, num_failed = get_results(log_dir / "results.xml")
    assert num_tests > 0 and num_failed == 0, (
        f"{num_failed} of {num_tests} cocotb tests failed, see {log_dir / 'sim.log'}")
    return log_dir
