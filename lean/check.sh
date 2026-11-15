#!/usr/bin/env bash
# Checks the Lean proofs of the checker algebra and saves the result under logs/.
# Needs Lean (installed with elan in ~/.elan; see docs/tools.md). Run:  lean/check.sh
set -u
cd "$(dirname "$0")"
ROOT="$(cd .. && pwd)"
export PATH="$HOME/.elan/bin:$PATH"
LOG="$ROOT/logs/$(date +%Y-%m-%dT%H%M%S)_lean"
mkdir -p "$LOG"
lean --version > "$LOG/run_info.txt"
lean AbftChecker.lean > "$LOG/lean.log" 2>&1
code=$?
{ echo "lean exit code: $code (0 = every theorem checked)";
  echo "uses of sorry in AbftChecker.lean: $(grep -c 'sorry' AbftChecker.lean)";
  grep -E "depends on axioms" "$LOG/lean.log"; } | tee "$LOG/summary.txt"
echo "log: $LOG"
exit $code
