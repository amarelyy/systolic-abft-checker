"""Extra fault injection: faults the first campaign (tb/test_injection.py) did not cover.

Groups (CAMP_N injections each, per design, width and seed; every multiply starts from a reset):
  control    one fault (bit flip or stuck-at) in the control logic: state, counter, the control's
             copies of A and B, the done pulse, and (WS) the captured result. Every flip-flop is
             equally likely.
  fsm        like control, but only the few flip-flops that steer the control: state, counter and
             the done pulse (7 bits), so that hangs and early or late results are well sampled.
  checker    one fault in the checker itself: its copies of A and B, the reference checksums, its
             counters and its output flags. Every flip-flop is equally likely.
  stall      one fault in a PE register (as in the first campaign) while the array is stalled at
             random (each cycle with probability 0.25).
  double     two independent faults in PE registers at the same time.
  free_stall no fault, random stalls: the false alarm rate under stalls.

Labels as in tb/injector.py. `no_result` means the control never produced `done` within the
timeout. For the groups with a healthy checker (stall, double, free_stall) the checker hardware
must agree with model/abft.py; for control and checker faults it need not.

Outputs, in the run's log folder and copied to results/: injection_extra.csv, campaign_extra.txt.

Run:  pytest tb/test_injection_extra.py      (env CAMP_N sets the count, default 1000)
"""

import csv
import os
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import cocotb
import numpy as np
import pytest
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge

from driver import random_matrix
from injector import C_DONE, Fault, classify, run_multiply_ext
from model.abft import check
from model.golden import matmul_golden
from run_util import ROOT, WIDTHS, run_cocotb
from targets import chk_targets, ctrl_targets, targets

N = 4
CAMP_N = int(os.environ.get("CAMP_N", 1000))
SEEDS = [12345, 54321]
SOURCES = ["pe.sv", "systolic_ws.sv", "systolic_ws_ctrl.sv", "pe_os.sv", "systolic_os.sv",
           "systolic_os_ctrl.sv", "abft_checker.sv", "top.sv"]
DESIGNS_TOP = {"ws": 0, "os": 1}
STALL_P = 0.25
GROUPS = ["control", "fsm", "checker", "stall", "double", "free_stall"]
HEALTHY = {"stall", "double", "free_stall"}          # groups where the checker itself is not faulted


def pe_fault(design, W, tgts):
    """A random fault in a PE register, chosen as in the first campaign."""
    t = random.choice(tgts)
    bit = random.randrange(t.width)
    cycle = random.randrange(C_DONE[design])
    if random.random() < 0.5:
        return Fault("flip", t, bit, cycle)
    return Fault("stuck", t, bit, cycle, length=random.randint(1, 8), value=random.randint(0, 1))


def flop_fault(design, tgts):
    """A random fault in a control or checker flip-flop; every flip-flop equally likely."""
    pick = random.randrange(sum(t.width for t in tgts))
    for t in tgts:
        if pick < t.width:
            bit = pick
            break
        pick -= t.width
    cycle = random.randrange(C_DONE[design] + 1)       # up to and including the check cycle
    if random.random() < 0.5:
        return Fault("flip", t, bit, cycle)
    return Fault("stuck", t, bit, cycle, length=random.randint(1, 8), value=random.randint(0, 1))


@cocotb.test()
async def test_extra(dut):
    W = int(dut.W.value)
    design = "ws" if int(dut.DATAFLOW.value) == 0 else "os"
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.stall.value = 0
    dut.start.value = 0
    dut.keep_w.value = 0
    dut.a_mat.value = 0
    dut.b_mat.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)

    pe_t, ctrl_t, chk_t = targets(design, W), ctrl_targets(design, W), chk_targets(design, W)
    handles = {}
    plan = [g for g in GROUPS for _ in range(CAMP_N)]
    random.shuffle(plan)
    rows, disagree, missed_log = [], 0, []

    for idx, group in enumerate(plan):
        A, B = random_matrix(), random_matrix()
        stall_p = STALL_P if group in ("stall", "free_stall") else 0.0
        if group == "control":
            faults = [flop_fault(design, ctrl_t)]
        elif group == "fsm":
            faults = [flop_fault(design, [t for t in ctrl_t if t.reg in ("state", "cnt", "done")])]
        elif group == "checker":
            faults = [flop_fault(design, chk_t)]
        elif group == "stall":
            faults = [pe_fault(design, W, pe_t)]
        elif group == "double":
            faults = [pe_fault(design, W, pe_t), pe_fault(design, W, pe_t)]
        else:
            faults = []
        res = await run_multiply_ext(dut, design, A, B, W, faults, handles, stall_p)
        golden = matmul_golden(A, B, W)
        if not res["done"]:
            label, changed, n_wrong = "no_result", "", ""
        else:
            diff = np.argwhere(res["C"] != golden)
            changed, n_wrong = int(len(diff) > 0), len(diff)
            label = classify(bool(changed), bool(res["flag"]))
            if group in HEALTHY:
                m_flag, m_row, m_col = check(res["C"], A, B, W)
                ok = (m_flag == bool(res["flag"])) and (
                    m_row is None or (res["loc_valid"] == 1 and (res["row"], res["col"]) == (m_row, m_col)))
                disagree += int(not ok)
        if res["done"] and label == "missed":
            missed_log.append(
                f"idx {idx} group {group} faults "
                f"{' + '.join(f'{f.kind}:{f.target.name}[{f.bit}]@{f.cycle}' for f in faults)}\n"
                f"  done at cycle {res['done_cycle']} (nominal {C_DONE[design]}), reference ready at done: "
                f"{res['ref_ready']}\n  A=\n{A}\n  B=\n{B}\n  C seen=\n{res['C']}\n  golden=\n{golden}\n"
                f"  ref_col={res['ref_col']:#x} ref_row={res['ref_row']:#x}")
        rows.append({
            "idx": idx, "group": group,
            "faults": " + ".join(f"{f.kind}:{f.target.name}[{f.bit}]@{f.cycle}" for f in faults),
            "target": faults[0].target.name if faults else "",
            "kind": faults[0].kind if faults else "",
            "done": int(res["done"]), "done_cycle": res["done_cycle"] or "",
            "ref_ready": res.get("ref_ready", ""), "chk_seen": int(res["chk_seen"]),
            "changed": changed, "n_wrong": n_wrong,
            "flag": res["flag"], "label": label,
        })

    with open("injection_extra.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    seed = os.environ.get("CAMP_SEED", "")
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    shutil.copy("injection_extra.csv", out / f"injection_extra_{design}_W{W}_s{seed}.csv")

    lines = [f"Extra fault injection, design = {design}, W = {W}, seed = {seed}, {CAMP_N} per group, "
             f"every multiply from a reset", ""]
    labels = ["masked", "detected", "missed", "no_result", "flag_without_change"]
    lines.append(f"  {'group':<12} {'n':>5} " + " ".join(f"{l:>19}" for l in labels) + f" {'coverage':>9}")
    for g in GROUPS:
        c = Counter(r["label"] for r in rows if r["group"] == g)
        n = sum(c.values())
        nchg = c["detected"] + c["missed"]
        cov = f"{100 * c['detected'] / nchg:.1f}%" if nchg else "n/a"
        lines.append(f"  {g:<12} {n:>5} " + " ".join(f"{c[l]:>19}" for l in labels) + f" {cov:>9}")
    lines.append("  (coverage = detected / (detected + missed); masked faults excluded)")
    lines.append("")
    for g, title in (("control", "Control faults by register"), ("fsm", "Control-state faults by register"),
                     ("checker", "Checker faults by register")):
        lines.append(title)
        by = defaultdict(Counter)
        for r in rows:
            if r["group"] == g:
                by[r["target"]][r["label"]] += 1
        lines.append(f"  {'register':<16} {'n':>5} " + " ".join(f"{l:>19}" for l in labels))
        for t in sorted(by):
            lines.append(f"  {t:<16} {sum(by[t].values()):>5} " + " ".join(f"{by[t][l]:>19}" for l in labels))
        lines.append("")
    free = [r for r in rows if r["group"] == "free_stall"]
    lines.append(f"Fault-free with stalls: {len(free)}, flagged: {sum(r['flag'] for r in free)}")
    lines.append(f"Checker hardware disagrees with model/abft.py (healthy-checker groups): {disagree}")
    late = Counter()
    for r in rows:
        if r["group"] == "fsm" and r["done"]:
            late[r["done_cycle"] == C_DONE[design]] += 1
    lines.append(f"Control-state faults where done still came at the nominal cycle: {late[True]}, at another "
                 f"cycle: {late[False]}")
    text = "\n".join(lines)
    Path("campaign_extra.txt").write_text(text + "\n")
    shutil.copy("campaign_extra.txt", out / f"campaign_extra_{design}_W{W}_s{seed}.txt")
    Path("missed_cases.txt").write_text("\n\n".join(missed_log) + ("\n" if missed_log else ""))
    if missed_log:
        shutil.copy("missed_cases.txt", out / f"missed_extra_{design}_W{W}_s{seed}.txt")
    dut._log.info("\n" + text)
    assert disagree == 0, "healthy checker disagrees with the model"
    assert not any(r["flag"] for r in free), "false alarm under stalls"


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("W", WIDTHS)
@pytest.mark.parametrize("design", DESIGNS_TOP)
def test_injection_extra_runner(design, W, seed):
    run_cocotb("top", SOURCES, "test_injection_extra", f"injection_extra_{design}_W{W}_s{seed}",
               parameters={"W": W, "DATAFLOW": DESIGNS_TOP[design]}, seed=seed, assertions=False)
