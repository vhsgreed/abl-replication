# Pre-registration: does abliteration's off-target optimism replicate on an open task?

Status: FROZEN 2026-10-15 at git tag `freeze-v1`. Confirmatory runs start only after this tag is public (see change log).
Author: Karl Sundström (agentrecourse.org), with Hermes Agent. Licence: code MIT, data CC BY 4.0.

## 0. Background and why this study exists

Fafuła (2026), "Abliteration Is Not a Scalpel" (arXiv 2607.17427, data DOI 10.5281/zenodo.21314839),
found that refusal-abliterated models make different decisions on a task with nothing to refuse:
abliterated Gemma-4-26B-A4B bet "up" +12.2 pp more often than its base (95% CI +8.5..+16.0), and wrote
longer self-critiques (+4.0 words), with the same signs in Qwen3-30B-A3B. Its inputs (proprietary analyst
briefs and debate transcripts) are not released, so the generation step cannot be re-run by anyone else.

This study re-tests the two cross-family findings on a fully open task anyone can regenerate, on two
serving stacks (BF16 on GPU, Q4_K_M on CPU). It is a conceptual replication: same model pair, same
abliteration author, same sampling settings and output schema; different (public, simpler) inputs.

## 1. Arms and provenance (fixed)

| arm | weights (HF, pinned revision) |
|---|---|
| base | google/gemma-4-26B-A4B-it @ 4d7ae4984b7db7de8f8457170b3f1a419ee76d52 |
| abl  | huihui-ai/Huihui-gemma-4-26B-A4B-it-abliterated @ bfa658000df7d734e0946595ab832abb7e34b1be |

- config.json, generation_config.json, tokenizer.json are byte-identical between the two repos (sha256 in
  `provenance/`). chat_template.jinja differs; the huihui template is never used. Both arms are prompted
  with raw text rendered by us from Google's template (sha256 ae53464b...), non-thinking mode, so the
  template embedded in a GGUF cannot affect either arm. The runner logs the rendered-prompt sha256 and the
  server's prompt token count per request; the smoke gate requires both to match across arms.
- Q4 stack: both arms converted with the same llama.cpp commit (fd55cb98fe29...) `convert_hf_to_gguf.py
  --outtype bf16`, then `llama-quantize ... Q4_K_M` with no imatrix; served by `llama-server` of the same
  commit on CPU (AMD Ryzen 9 7940HS, 8 threads). GGUF sha256 recorded in `harness/arms.json`.
- BF16 stack: same weights, served in BF16 on a rented GPU (vLLM or llama.cpp CUDA, recorded at run time),
  same rendered prompts and sampling.

## 2. Task (open, regenerable)

- 40 large-cap stocks in two independent segments: US (20 Dow/S&P names) and EU (20 Euro Stoxx /
  FTSE / SMI names). Benchmarks SPY and EURO STOXX 50. Public daily prices (Yahoo chart API), raw JSON
  committed in `data/raw/`; `task/build_cells.py` builds `data/cells.jsonl` deterministically
  (sha256 71cec3da...).
- Grid: 24 Friday decision dates 2026-04-24 .. 2026-10-02, x 20 tickers = 480 cells per segment.
  Smoke dates 2026-04-10 and 2026-04-17 (80 cells) are used for pipeline tests only and never scored.
- One frozen prompt (`task/prompt_v1.md`, sha256 recorded in every output row) asks for one JSON object:
  stance bull/bear, time_horizon, thesis, 2-4 key_risks, confession (strongest fact against own call),
  reversal_trigger, confidence, p_wrong. Field order and probes follow the original study's schema.
- Sampling, identical for both arms: temperature 1.0, top_k 64, top_p 0.95 (Gemma's generation_config
  and the original study's values); every other sampler disabled explicitly; n_predict 768.
  Seeds: sha256(cell|sample|attempt), shared by both arms (common random numbers).

## 3. Hypotheses (primary; everything else is exploratory)

- **H1 optimism.** Share of bull stances, abl minus base, is > 0.
- **H2 verbosity.** Confession length in words, abl minus base, is > 0.
- **H3 survives quantization.** H1 holds on the Q4_K_M CPU stack (the format most users run).

Exploratory, reported with CIs but no verdict: mean confidence (opposite signs in the original), the
confidence <= 0.60 tail, p_wrong vs 1 - confidence coherence, horizon share, thesis length, flip rate
across samples, per-arm Q4-vs-BF16 shift in bull rate, hit rate and signed return of next-week outcome
(Monday open to Friday close), and a community-quantized GGUF of the abl arm.

## 4. Statistics and replication criteria (each primary must meet all that apply)

Unit: the cell (stock x week). Per arm and cell, average the valid samples; take the paired difference
abl - base per cell. CI: cluster bootstrap over the 24 weeks, B = 5000, seed 20261015, percentile,
**98.33% two-sided** (Bonferroni over 3 primaries).

1. **Direction and certainty:** the CI excludes 0 on the predicted side. Opposite-side CI = OPPOSITE,
   otherwise NULL.
2. **Both stacks:** H1 and H2 must pass on BF16 and on Q4. (H3 is the Q4 arm of H1 by definition.)
3. **Both segments:** each must pass in US and in EU separately.

A hypothesis is "replicated" only if every applicable criterion passes. Effect size is not a criterion;
we report ours next to the original (+12.2 pp, +4.0 words).

Power (synthetic self-test, `analysis/score.py --selftest`, committed output): with 480 cells, 24
week-clusters and a strong shared week effect, 3 samples per cell gives 88% power at +6 pp and ~100% at
+12 pp; null false-pass rate 0.5-1.5% one-sided (nominal 0.83%).

**Sample size and stopping rule:** 3 samples per cell per arm per stack per segment. A run continues
across nights (resumable) until every cell has 3 completed samples in both arms. No primary outcome is
computed before that. Health counts (validity, failure types, throughput) may be inspected at any time.

**Order (gated):** Q4/US first, then Q4/EU. BF16 runs both segments on rented GPU (< $20 per action).
If H1 is NULL or OPPOSITE on Q4/US, the remaining runs still happen and are reported; there is no rescue.

**NOT SCORABLE** if a segment has < 400 paired cells, or an arm's final-invalid rate exceeds 2%.

## 5. Output validity (smoke gate before any grid run)

Every response is checked by `harness/validate.py` (19 synthetic known-answer tests in
`harness/test_validate.py`). Failures: empty, truncated (stop_type != eos), reasoning or chat-control
token in the visible text, text outside the JSON, parse error, missing/extra field, enum or range
violation, fewer than 3 words in a text field, key_risks outside 2-4. Invalid outputs are retried with a
new seed up to 3 attempts; first-attempt validity is reported per arm as a capability covariate.

Smoke gate (smoke cells only, both arms, 1 sample): first-attempt valid >= 95% per arm; zero reasoning
leaks; zero truncations; rendered-prompt sha256 and prompt token count identical across arms for every
cell; output tokens p99 < 400. Two live negative controls must fail as designed: n_predict 24 must be
caught as truncated, and a thinking-mode render must be caught as a reasoning leak.

## 6. Study 2: Ajax audit (frozen now, run when official weights are published)

Ajax (PewDiePie / odysseus-dev) is announced as a Heretic-decensored Qwen3.5-9B. Arms: Qwen/Qwen3.5-9B
@ c202236235762e1c871ad0ccb60c8ee5ba337b9a vs the first official Ajax BF16 release; both quantized by us
with one llama.cpp commit (Q4_K_M), non-thinking mode.

- **H4 math damage.** Exact-match accuracy on the first 300 items of the GSM8K test split (shuffled with
  seed 20261015), greedy decoding, abl minus base < 0. Bootstrap over items, 97.5% CI (Bonferroni over 2).
- **H5 optimism.** H1 on the US grid, 3 samples, 97.5% CI.
Only criteria 1 applies (single stack, US segment). If no official weights exist by 2027-04-15 the study
is closed as not run.

## 7. Deviations and change log

Any change after `freeze-v1` is appended below with date and reason; earlier text is never edited.
Bugs found in harness or scorer get an errata entry committed before the re-run.

- 2026-10-15: draft.
- 2026-10-15 (before freeze): a first grid run `grid1` (16:48-20:42 CEST, 515 decisions: base 195,
  abl 320, sample 0 only) was generated from the plan as committed locally at 3746fb1..e9f18ed, BEFORE
  the repository was public. Because a local git timestamp cannot be verified by outsiders, `grid1` is
  set aside as a PILOT: it is excluded from every confirmatory test and reported separately as a pilot.
  Only health checks were run on it (validity, token counts, prompt/seed identity via
  `harness/health.py`); no arm comparison of stance, confession length or confidence was computed.
  Confirmatory data = run `grid2` and later, all started after the public push of tag `freeze-v1`.
- 2026-10-15 (before freeze): pilot health showed both arms use only confidence values 0.55/0.60/0.65
  and p_wrong = 1 - confidence in every output. Neither is a primary outcome; the exploratory confidence
  analyses will be coarse and are reported as such. No change to H1-H3 or the criteria.
- 2026-10-15 (before freeze): runner hardening after an OOM incident (own capped systemd unit, yields
  to Ollama), and stripping of the single trailing end-of-turn token before validation. Validator rules
  unchanged; both changes predate all grid output.
- 2026-10-17: publication impact metric registered (added post-freeze; touches no hypothesis, bar or
  analysis). PRIMARY: within 90 days of the article going live, at least one of (a) a reply, issue or
  citation from the authors of arXiv 2607.17427 / Zenodo 10.5281/zenodo.21314839, (b) inclusion in a
  curated refusal-suppression index (e.g. ant-research/Awesome-Refusal-Suppression), (c) a named
  mention in an AI-safety or interpretability newsletter or podcast. Route (a) is the target: the
  study replicates a generation step their data release cannot re-run. SECONDARY (not scored): one
  Hacker News or r/LocalLLaMA thread clearing 100 points. TRACKED ONLY: umami visits, repo clones.
- 2026-10-17: packaging fixed as part of the deliverable: arXiv cross-post (cs.CL) plus a HuggingFace
  papers listing, in addition to the public repo, frozen prompts and the one-command regeneration,
  because all three acknowledgment routes reward those artifacts.
- 2026-10-17: pilot disclosure. Refusal-boundary pilots (~/abliteration-study/pilot-1: 24 framed
  journaling probes; pilot-2: 1,200 bare runs on XSTest/AdvBench/HarmBench across two model pairs,
  seed 42) measure REFUSAL RATES, a different axis from H1-H3, and are excluded from every test in
  this study. Their finding (aligned over-refusal 2-8%, abliteration drops harmful refusal 72-98 pp,
  role framing collapses refusals to 0/16) is pilot evidence for a candidate Study 3 (over-refusal
  equivalence, safety-refusal delta, framing factor), which is NOT registered here and NOT authorized
  to run before grid2 and the queued LittleBit study are done.
- 2026-10-19 (before any BF16 data): harness extended for the BF16 stack this plan registered in
  s1. `harness/run.py` can now drive a remote llama-server via ABL_REMOTE_BASE / ABL_REMOTE_ABL
  base URLs (SSH tunnels to a rented box serving the BF16 GGUFs) and records a `stack` field per
  row (ABL_STACK, default "q4-local"). Request bodies, seeds, prompts and sampling are
  byte-identical to the local path; with the env unset the Q4 behaviour is unchanged. Reason:
  the frozen runner only spawned a local CPU llama-server. Scorer self-test re-run green after
  the change. No hypothesis, bar or criterion touched.
- 2026-10-19 (Tier-0 smoke of the remote path, free on geekom): 4/4 smoke decisions valid
  first-try through ABL_REMOTE_* URLs; render-sha and seed parity across arms exact; row `stack`
  recorded; negative control (n_predict 24) caught as truncated on all 3 attempts. Remote plumbing
  cleared before any metered minute. BF16 GGUF sha256 recorded in provenance/bf16_gguf_sha256.txt
  (google e59819d3..., huihui 5af66a95...); box conversions must match these.
- 2026-10-19 (box smoke gate, on instance 56690152): box GGUF conversions are BYTE-IDENTICAL to
  geekom's (sha256 both arms match provenance exactly). Pitfall found and fixed before scoring:
  the GGUF metadata embeds the source directory basename, so converting from differently named
  dirs produced same-size-but-different files; re-converted from dirs named exactly as geekom's
  checkouts. Servers: GPU0 base :18080, GPU1 abl :18081 (BF16, -np 4). Smoke via the remote
  path: 16/16 valid first-try at np=1 and np=4, render-sha and seed parity exact, prompt-token
  parity per cell; negative controls both caught (ctl_trunc -> truncated:limit on 8/8; ctl_think
  -> reasoning_or_control_leak on 8/8). Gate PASS. Full run `grid_bf16` launched 10:52 CEST
  (unit abl-grid_bf16, ABL_STACK=bf16-vast-2xA100SXM4, np=4): ~2 s/decision aggregate,
  5,760 decisions, ETA ~3.2h, projected run cost ~$11 of the $25 credit (setup ~$5 so far).
