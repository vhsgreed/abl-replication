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

Rerun: download the two pinned HF revisions in `PLAN.md`, convert and quantize them with the pinned
llama.cpp commit, fill `harness/arms.json`, then `harness/run.py --run myrun --split grid --samples 3`.
