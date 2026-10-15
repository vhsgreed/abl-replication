#!/usr/bin/env bash
# Launch any experiment step in its OWN systemd user unit, never inside the Hermes app's cgroup.
# Why: on 2026-10-15 a llama-server started from a Hermes terminal lived in the Hermes desktop's
# scope (OOMPolicy=stop). Kernel global OOM killed it, and systemd then stopped the whole scope,
# taking Hermes down. Here: own cgroup, hard memory cap, and we are the preferred OOM victim.
#   launch.sh <unit-name> <command...>
set -euo pipefail
name="$1"; shift
systemd-run --user --unit="abl-$name" --collect \
  -p MemoryHigh=19G -p MemoryMax=20G -p MemorySwapMax=1G \
  -p OOMScoreAdjust=900 -p OOMPolicy=continue \
  -p Restart=on-failure -p RestartSec=90 \
  --working-directory="$HOME/src/abl-replication" \
  -E PYTHONUNBUFFERED=1 \
  "$@"
echo "started abl-$name; logs: journalctl --user -u abl-$name -f"
