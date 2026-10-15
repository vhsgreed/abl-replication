#!/usr/bin/env bash
# Unattended afternoon prep 2026-10-15, hard stop 17:45 (Karl uses the machine from 18:00).
# Order keeps exactly one model in RAM at a time. Every step is idempotent so a rerun resumes.
set -uo pipefail
cd "$HOME/src/abl-replication"
DL=2026-10-15T17:45
PY=.venv/bin/python
HF=$HOME/models/hf; GG=$HOME/models/gguf; LC=$HOME/src/llama.cpp
ABL=$HF/huihui-gemma-4-26B-A4B-it-abliterated
ABLB=$GG/huihui-gemma-4-26B-A4B-it-abliterated-BF16.gguf
ABLQ=$GG/huihui-gemma-4-26B-A4B-it-abliterated-Q4_K_M.gguf
mkdir -p out
log(){ echo "$(date +%T) $*" >> out/prep.log; sync; }
late(){ [[ $(date +%s) -ge $(date -d "${DL/T/ }" +%s) ]]; }
CTL=$($PY -c "import sys;sys.path.insert(0,'harness');from render import load_cells;print(','.join(c['cell_id'] for c in load_cells('smoke')[::10]))")

log "START prep (deadline $DL)"
log "1 base smoke: 80 cells x 1 sample"
$PY harness/run.py --run smoke1 --split smoke --samples 1 --arms base --deadline $DL >> out/prep.log 2>&1
log "1 done rc=$?"

log "2 abl weights: wait for download unit, then verify/resume"
while systemctl --user is-active -q abl-dl-huihui; do late && { log "deadline in step 2"; exit 0; }; sleep 30; done
for i in 1 2 3 4 5; do
  (cd "$HF" && uvx --from "huggingface_hub[hf_xet]" hf download huihui-ai/Huihui-gemma-4-26B-A4B-it-abliterated \
     --revision bfa658000df7d734e0946595ab832abb7e34b1be --local-dir "$ABL" >> dl_huihui.log 2>&1) && break
  log "download attempt $i failed, retry in 60 s"; sleep 60; late && exit 0
done
$PY harness/verify_weights.py >> out/prep.log 2>&1 || { log "ERROR weight verification failed"; exit 1; }
log "2 weights verified"

if [[ ! -s $ABLQ ]]; then
  log "3 convert + quantize abl (same llama.cpp commit and flags as base)"
  (cd "$LC" && .venv-convert/bin/python convert_hf_to_gguf.py "$ABL" --outtype bf16 --outfile "$ABLB" > "$GG/convert_huihui.log" 2>&1) \
    || { log "ERROR convert failed"; exit 1; }
  "$LC/build/bin/llama-quantize" "$ABLB" "$ABLQ.tmp" Q4_K_M 16 > "$GG/quant_huihui.log" 2>&1 && mv "$ABLQ.tmp" "$ABLQ" \
    || { log "ERROR quantize failed"; exit 1; }
fi
S=$(sha256sum "$ABLQ" | cut -d' ' -f1)
$PY - "$ABLQ" "$S" <<'E'
import json, sys
p = "harness/arms.json"; d = json.load(open(p)); d["abl"] = {"gguf": sys.argv[1], "sha256": sys.argv[2]}
json.dump(d, open(p, "w"), indent=1)
E
log "3 abl Q4_K_M ready sha256=$S"

late && { log "deadline before abl smoke"; exit 0; }
log "4 abl smoke: 80 cells x 1 sample"
$PY harness/run.py --run smoke1 --split smoke --samples 1 --arms abl --deadline $DL >> out/prep.log 2>&1
log "4 done rc=$?"

log "5 negative controls on cells $CTL"
$PY harness/run.py --run ctl_trunc --split smoke --cells "$CTL" --samples 1 --arms abl,base --n-predict 24 --attempts 1 --deadline $DL >> out/prep.log 2>&1
$PY harness/run.py --run ctl_think --split smoke --cells "$CTL" --samples 1 --arms base,abl --thinking --attempts 1 --deadline $DL >> out/prep.log 2>&1
log "5 done"
$PY harness/smoke_report.py > /dev/null 2>&1; log "GATE $(tail -1 out/smoke_report.md)"

log "6 extra smoke samples (stability + throughput) until deadline"
$PY harness/run.py --run smoke1 --split smoke --samples 3 --arms base,abl --deadline $DL >> out/prep.log 2>&1
$PY harness/smoke_report.py > /dev/null 2>&1; log "FINAL $(tail -1 out/smoke_report.md)"
log "END prep"
