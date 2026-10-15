#!/usr/bin/env bash
# Watch the smoke gate and launch the first grid run the moment it passes.
# On gate FAIL: log the decision and exit 0 (no launch, no restart loop).
set -uo pipefail
cd "$HOME/src/abl-replication"
P=out/prep.log
# wait for the gate verdict line (written right after the negative controls)
for i in $(seq 240); do
  grep -q " GATE " "$P" 2>/dev/null && break
  systemctl --user is-active -q abl-prep || break          # prep died early
  sleep 30
done
V=$(grep " GATE " "$P" 2>/dev/null | tail -1)
if [[ -z "$V" ]]; then
  echo "$(date +%T) no gate verdict (prep exited early: $(tail -2 $P | tr '\n' ' '))" >> out/launch_decision.log; exit 0
fi
echo "$(date +%T) gate: $V" >> out/launch_decision.log
case "$V" in
  *PASS*)
    systemctl --user stop abl-prep 2>/dev/null || true     # free CPU for the grid run
    sleep 5
    echo "$(date +%T) LAUNCH grid1 (samples 3, deadline 2026-10-16T15:50)" >> out/launch_decision.log
    exec .venv/bin/python harness/run.py --run grid1 --split grid --samples 3 \
         --block-weeks 4 --deadline 2026-10-16T15:50 ;;
  *)
    echo "$(date +%T) GATE FAILED - not launching" >> out/launch_decision.log; exit 0 ;;
esac
