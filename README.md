# abl-replication

Pre-registered conceptual replication of "Abliteration Is Not a Scalpel" (arXiv 2607.17427) on a fully
open task: does refusal-abliteration make Gemma-4-26B-A4B more optimistic and more verbose on harmless
weekly stock-direction decisions, and does that survive Q4_K_M quantization on CPU?

- `PLAN.md` is the pre-registration. It is frozen at tag `freeze-v1`; later changes are appended to its
  change log only. Confirmatory data are generated only after that tag was public.
- `task/` builds the 960 decision cells from public daily prices (`data/raw/`) and holds the frozen prompt.
- `harness/` renders prompts, serves each arm with llama-server, validates every output
  (`validate.py`, tests in `test_validate.py`), and runs the smoke gate.
- `analysis/score.py` is the registered scorer (`--selftest` = synthetic power and null checks).
  Its outputs (`out/grid2/score.json`, `out/grid_bf16/score.json`) are the committed numbers the
  article quotes; `analysis/figures.py` rebuilds every article figure and `effects.csv` from
  exactly those two files.
- The BF16 segment ran on a rented GPU through `harness/run.py` in remote mode
  (`ABL_REMOTE_BASE`/`ABL_REMOTE_ABL` pointing at llama-server instances serving the BF16
  conversions; `ABL_STACK` labels each row). `harness/box_setup.sh` is the box-side setup, gated
  on the GGUF sha256 matching `provenance/bf16_gguf_sha256.txt`; `provenance/bf16_stack.json`
  records the serving stack as required by the plan.

Rerun: download the two pinned HF revisions in `PLAN.md`, convert and quantize them with the pinned
llama.cpp commit, fill `harness/arms.json`, then `harness/run.py --run myrun --split grid --samples 3`.
Not reproducible from public data: nothing in the scored results; the pilot `grid1` and the
refusal pilots discussed in the change log are separate, excluded materials.
