#!/usr/bin/env bash
# Runs every formal task that is expected to finish and saves the results under logs/.
# Run:  source env.sh && formal/run_all.sh
set -u
cd "$(dirname "$0")"
ROOT="$(cd .. && pwd)"
LOG="$ROOT/logs/$(date +%Y-%m-%dT%H%M%S)_formal"
mkdir -p "$LOG"
{ yosys -V; sby --version 2>&1 | head -1; for s in z3 boolector yices bitwuzla; do echo -n "$s: "; $s --version 2>&1 | head -1; done; } > "$LOG/run_info.txt" 2>&1
printf '%-22s %-10s %s\n' file task result | tee "$LOG/summary.txt"
run() {   # file task
    rm -rf "${1%.sby}_$2"
    sby -f "$1" "$2" > "$LOG/${1%.sby}_$2.log" 2>&1
    result=$(grep -oE "DONE \((PASS|FAIL|ERROR)[^)]*\)" "$LOG/${1%.sby}_$2.log" | tail -1)
    printf '%-22s %-10s %s\n' "$1" "$2" "$result" | tee -a "$LOG/summary.txt"
}
for t in ws_w16 ws_w18 ws_w32 os_w16 os_w18 os_w32 cover_ws cover_os; do run pe_props.sby $t; done
for t in ws_w16 ws_w18 ws_w32 os_w16 os_w18 os_w32 cover_ws cover_os; do run handshake.sby $t; done
for t in proto cover; do run checker_props.sby $t; done
echo "log: $LOG"
