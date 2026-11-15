"""Fault injection into the PE registers of the array, with the ABFT checker watching.

  test_known_flip   A flip whose effect is known in advance, to check injector and classifier.
                    Weight-stationary: bit 5 of psum_out of PE[3][0] holds C[i][0] at four
                    cycles (one per row i); a flip there must change exactly C[i][0] by +-32 and
                    be detected and located, and a flip at any other cycle must be masked.
                    Output-stationary: bit 5 of acc of PE[0][0] stays in the accumulator, so a
                    flip at any cycle must change exactly C[0][0] by +-32.
  test_campaign     Random campaign: CAMP_N bit flips, CAMP_N stuck-at faults and CAMP_N
                    fault-free multiplies per design and width, fixed seed. Every injection
                    gets a label (masked / detected / missed). The checker hardware's answer is
                    also compared with model/abft.py.

Outputs, in the run's log folder and copied to results/: injection.csv (one row per injection)
and campaign.txt (summary tables).

Run:  pytest tb/test_injection.py        (env CAMP_N sets the count, default 1000)
"""

import csv
import os
import random
import shutil
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import cocotb
import numpy as np
import pytest
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge

from driver import random_matrix
from injector import C_DONE, Fault, classify, run_multiply
from model.abft import check
from model.golden import matmul_golden
from run_util import ROOT, WIDTHS, run_cocotb
from targets import targets

N = 4
CAMP_N = int(os.environ.get("CAMP_N", 1000))
SOURCES = ["pe.sv", "systolic_ws.sv", "systolic_ws_ctrl.sv", "pe_os.sv", "systolic_os.sv",
           "systolic_os_ctrl.sv", "abft_checker.sv", "top.sv"]
DESIGNS_TOP = {"ws": 0, "os": 1}


async def start(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.stall.value = 0
    dut.start.value = 0
    dut.keep_w.value = 0
    dut.a_mat.value = 0
    dut.b_mat.value = 0
    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


def design_of(dut):
    return "ws" if int(dut.DATAFLOW.value) == 0 else "os"


@cocotb.test()
async def test_known_flip(dut):
    W, design = int(dut.W.value), design_of(dut)
    await start(dut)
    A, B = random_matrix("uniform"), random_matrix("uniform")
    golden = matmul_golden(A, B, W)
    mask = (1 << W) - 1
    if design == "ws":
        target = next(t for t in targets("ws", W) if (t.row, t.col, t.reg) == (3, 0, "psum_out"))
    else:
        target = next(t for t in targets("os", W) if (t.row, t.col, t.reg) == (0, 0, "acc"))
    hits = {}                                    # cycle -> (changed positions, label)
    for cycle in range(C_DONE[design]):
        res = await run_multiply(dut, design, A, B, W, Fault("flip", target, 5, cycle))
        diff = np.argwhere(res["C"] != golden).tolist()
        label = classify(bool(diff), bool(res["flag"]))
        if diff:
            assert len(diff) == 1, f"cycle {cycle}: {len(diff)} elements changed"
            i, j = diff[0]
            delta = (int(res["C"][i, j]) - int(golden[i, j])) & mask
            assert delta in (32, (1 << W) - 32), f"cycle {cycle}: change {delta} is not +-32"
            assert label == "detected" and res["loc_valid"] == 1 and (res["row"], res["col"]) == (i, j)
        hits[cycle] = (diff, label)
    changed_cycles = [c for c, (d, _) in hits.items() if d]
    dut._log.info(f"[{design} W={W}] cycles that changed C: {changed_cycles}; labels: "
                  f"{dict(Counter(l for _, l in hits.values()))}")
    if design == "ws":
        assert len(changed_cycles) == N, "WS: exactly four cycles hold a result in PE[3][0]"
        assert sorted(hits[c][0][0] for c in changed_cycles) == [[i, 0] for i in range(N)]
    else:
        assert len(changed_cycles) == C_DONE[design], "OS: accumulator keeps the flip at any cycle"
        assert all(hits[c][0] == [[0, 0]] for c in changed_cycles)
    assert all(l in ("detected", "masked") for _, l in hits.values())


def random_fault(design, W, kind, tgts):
    t = random.choice(tgts)
    bit = random.randrange(t.width)
    cycle = random.randrange(C_DONE[design])
    if kind == "flip":
        return Fault("flip", t, bit, cycle)
    return Fault("stuck", t, bit, cycle, length=random.randint(1, 8), value=random.randint(0, 1))


@cocotb.test()
async def test_campaign(dut):
    W, design = int(dut.W.value), design_of(dut)
    await start(dut)
    tgts = targets(design, W)
    handles = {}
    rows, disagree = [], 0

    plan = [("flip", f) for f in [True] * CAMP_N] + [("stuck", f) for f in [True] * CAMP_N] \
        + [("none", None)] * CAMP_N
    random.shuffle(plan)
    for idx, (kind, _) in enumerate(plan):
        A, B = random_matrix(), random_matrix()
        fault = random_fault(design, W, kind, tgts) if kind != "none" else None
        res = await run_multiply(dut, design, A, B, W, fault, handles)
        golden = matmul_golden(A, B, W)
        diff = np.argwhere(res["C"] != golden)
        changed = len(diff) > 0
        label = classify(changed, bool(res["flag"]))
        m_flag, m_row, m_col = check(res["C"], A, B, W)       # the Python model's answer
        agrees = (m_flag == bool(res["flag"])) and (
            m_row is None or (res["loc_valid"] == 1 and (res["row"], res["col"]) == (m_row, m_col)))
        disagree += int(not agrees)
        loc_ok = ""
        if len(diff) == 1:
            loc_ok = int(res["loc_valid"] == 1 and (res["row"], res["col"]) == tuple(diff[0]))
        rows.append({
            "idx": idx, "kind": kind,
            "target": fault.target.name if fault else "", "class": fault.target.cls if fault else "",
            "bit": fault.bit if fault else "", "ghost": int(fault.target.is_ghost(fault.bit)) if fault else "",
            "cycle": fault.cycle if fault else "", "length": fault.length if fault and kind == "stuck" else "",
            "value": fault.value if fault and kind == "stuck" else "",
            "changed": int(changed), "n_wrong": len(diff),
            "rows_hit": len(set(diff[:, 0])) if changed else 0, "cols_hit": len(set(diff[:, 1])) if changed else 0,
            "flag": res["flag"], "single_located_ok": loc_ok, "label": label, "model_agrees": int(agrees),
        })

    # ---------------------------------------------------------------- files
    with open("injection.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    shutil.copy("injection.csv", out / f"injection_{design}_W{W}.csv")

    lines = [f"Fault injection campaign, design = {design}, W = {W}, {CAMP_N} flips, {CAMP_N} stuck-at, "
             f"{CAMP_N} fault-free, no stalls", ""]

    def table(title, group_of, subset):
        lines.append(title)
        lines.append(f"  {'group':<22} {'injected':>8} {'masked':>7} {'detected':>9} {'missed':>7} "
                     f"{'coverage':>9} {'masked %':>9}")
        groups = defaultdict(list)
        for r in subset:
            groups[group_of(r)].append(r["label"])
        for g in sorted(groups):
            c = Counter(groups[g])
            nchg = c["detected"] + c["missed"]
            cov = f"{100 * c['detected'] / nchg:.1f}%" if nchg else "n/a"
            lines.append(f"  {str(g):<22} {len(groups[g]):>8} {c['masked']:>7} {c['detected']:>9} "
                         f"{c['missed']:>7} {cov:>9} {100 * c['masked'] / len(groups[g]):>8.1f}%")
        lines.append("")

    inj = [r for r in rows if r["kind"] != "none"]
    table("By fault kind (coverage = detected / (detected + missed); masked faults excluded)",
          lambda r: r["kind"], inj)
    table("By register class", lambda r: f"{r['kind']} / {r['class']}", inj)
    if W > 18:
        accs = [r for r in inj if r["class"] == "acc"]
        table("Accumulator bits: real bits vs ghost bits (copies of the sign bit)",
              lambda r: "ghost bit" if r["ghost"] else "real bit", accs)
    free = [r for r in rows if r["kind"] == "none"]
    flagged = sum(r["flag"] for r in free)
    lines.append(f"Fault-free multiplies: {len(free)}, flagged: {flagged}  -> false alarm rate "
                 f"{flagged / len(free):.4f}")
    c = Counter(r["label"] for r in inj)
    nchg = c["detected"] + c["missed"]
    lines.append(f"All injections: {len(inj)}, masked {c['masked']}, detected {c['detected']}, "
                 f"missed {c['missed']}, flag_without_change {c['flag_without_change']}")
    lines.append(f"Detection coverage = {c['detected']}/{nchg} = "
                 f"{100 * c['detected'] / nchg:.2f}%   (false alarm rate {flagged / len(free):.4f}, same table)")
    lines.append("Detection latency (cycles from result valid to error flag): 1 in every run "
                 "(asserted in run_multiply)")
    single = [r for r in inj if r["n_wrong"] == 1]
    lines.append(f"Faults that changed exactly one element: {len(single)}, checker located the element: "
                 f"{sum(r['single_located_ok'] for r in single)}")
    sizes = Counter(r["n_wrong"] for r in inj if r["changed"])
    lines.append("Changed elements per injection (how many outputs one fault corrupted): "
                 + ", ".join(f"{k}: {v}" for k, v in sorted(sizes.items())))
    lines.append(f"Checker hardware disagrees with model/abft.py in {disagree} of {len(rows)} multiplies")
    text = "\n".join(lines)
    Path("campaign.txt").write_text(text + "\n")
    shutil.copy("campaign.txt", out / f"campaign_{design}_W{W}.txt")
    dut._log.info("\n" + text)
    assert disagree == 0
    assert flagged == 0, "false alarm on a fault-free multiply"
    assert c["flag_without_change"] == 0


@pytest.mark.parametrize("W", WIDTHS)
@pytest.mark.parametrize("design", DESIGNS_TOP)
def test_injection_runner(design, W):
    run_cocotb("top", SOURCES, "test_injection", f"injection_{design}_W{W}",
               parameters={"W": W, "DATAFLOW": DESIGNS_TOP[design]}, assertions=False)
