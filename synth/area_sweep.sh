#!/usr/bin/env bash
# Pre-study: Yosys cell count of the 4x4 WS array (no checker) for several W.
# Generic gates only, no real cell library, so compare the numbers with each other only.
# Full synthesis results, with a real cell library and timing, will be added later.
#
# Run:  source env.sh && synth/area_sweep.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/logs/$(date +%Y-%m-%dT%H%M%S)_area_sweep"
mkdir -p "$LOG"
yosys -V > "$LOG/run_info.txt"

printf '%-4s %-10s %-10s\n' W cells flipflops | tee "$LOG/summary.txt"
for W in 16 17 18 20 24 32; do
    yosys -q -l "$LOG/yosys_W$W.log" -p "
        read_verilog -sv -DSYNTHESIS $ROOT/rtl/pe.sv $ROOT/rtl/systolic_ws.sv
        chparam -set W $W systolic_ws
        synth -flatten -top systolic_ws
        tee -o $LOG/stat_W$W.txt stat
    "
    cells=$(grep -E '^ +[0-9]+ +cells$|Number of cells:' "$LOG/stat_W$W.txt" | tail -1 | grep -oE '[0-9]+' | head -1)
    ffs=$(grep -E '\$_.*DFF' "$LOG/stat_W$W.txt" | grep -oE '^ *[0-9]+' | paste -sd+ | bc)
    printf '%-4s %-10s %-10s\n' "$W" "$cells" "$ffs" | tee -a "$LOG/summary.txt"
done
echo "log: $LOG"
