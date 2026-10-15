#!/usr/bin/env python3
"""Smoke gate report (PLAN.md section 5). Reads out/smoke1 and the two negative-control runs.
Writes out/smoke_report.md and exits 0 always; the verdict line says PASS or FAIL."""
import collections, json, pathlib, statistics as st

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"


def rows(run, arm):
    f = OUT / run / f"{arm}.jsonl"
    return [json.loads(l) for l in f.open()] if f.exists() else []


def pct(a, b):
    return f"{100 * a / b:.1f}%" if b else "n/a"


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None


L, gate = [], []
L.append("# Smoke report\n")
data = {arm: rows("smoke1", arm) for arm in ("base", "abl")}
for arm, rs in data.items():
    if not rs:
        L.append(f"## {arm}: no rows\n"); gate.append((f"{arm} has rows", False)); continue
    s0 = [r for r in rs if r["sample"] == 0]
    first = sum(r["first_attempt_ok"] for r in s0)
    atts = [a for r in rs for a in r["attempts"]]
    fails = collections.Counter(f.split(":")[0] for a in atts for f in a["failures"])
    leaks = sum(any("leak" in f for f in a["failures"]) for a in atts)
    truncs = sum(any(f.startswith("truncated") for f in a["failures"]) for a in atts)
    otoks = [a["out_tokens"] for a in atts if a["out_tokens"] is not None]
    walls = [a["wall_s"] for a in atts]
    ok = [r for r in rs if r["ok"]]
    bull = sum(r["result"]["bull"] for r in ok)
    fenced = sum(r["result"]["fenced"] for r in ok)
    hours = sum(walls) / 3600
    L.append(f"## {arm}\n- rows {len(rs)} (sample 0: {len(s0)}), attempts {len(atts)}, final valid {pct(len(ok), len(rs))}")
    L.append(f"- first-attempt valid (sample 0): {first}/{len(s0)} = {pct(first, len(s0))}")
    L.append(f"- failure counts over all attempts: {dict(fails) or 'none'}")
    L.append(f"- reasoning/control leaks: {leaks}; truncations: {truncs}")
    L.append(f"- output tokens p50 {q(otoks, .5)} p99 {q(otoks, .99)} max {max(otoks)}; wall s/attempt p50 {q(walls, .5)}")
    L.append(f"- throughput {len(rs) / hours:.0f} decisions/hour; bull share {pct(bull, len(ok))}; fenced JSON {pct(fenced, len(ok))}\n")
    gate += [(f"{arm} first-attempt valid >= 95%", len(s0) > 0 and first / len(s0) >= .95),
             (f"{arm} zero leaks", leaks == 0), (f"{arm} zero truncations", truncs == 0),
             (f"{arm} out tokens p99 < 400", q(otoks, .99) < 400)]

# cross-arm prompt identity
b = {(r["cell_id"], r["sample"]): r for r in data["base"]}
a = {(r["cell_id"], r["sample"]): r for r in data["abl"]}
common = sorted(set(a) & set(b))
sha_bad = [k for k in common if a[k]["prompt_render_sha"] != b[k]["prompt_render_sha"]]
tok_bad = [k for k in common if a[k]["attempts"][0]["prompt_tokens"] != b[k]["attempts"][0]["prompt_tokens"]]
L.append(f"## Cross-arm identity\n- paired (cell, sample): {len(common)}; render sha mismatches {len(sha_bad)}; prompt-token mismatches {len(tok_bad)} {tok_bad[:3]}\n")
gate += [("paired rows >= 80", len(common) >= 80), ("render sha identical across arms", not sha_bad),
         ("prompt tokens identical across arms", not tok_bad)]

# stability across samples (exploratory, smoke only)
for arm, rs in data.items():
    by = collections.defaultdict(list)
    for r in rs:
        if r["ok"]:
            by[r["cell_id"]].append(r["result"]["stance"])
    multi = [v for v in by.values() if len(v) >= 2]
    if multi:
        flips = sum(len(set(v)) > 1 for v in multi)
        L.append(f"- {arm}: cells with >=2 samples {len(multi)}, stance differs across samples in {pct(flips, len(multi))}")

# negative controls: each must be CAUGHT
L.append("\n## Negative controls (must be caught)")
for run, want in (("ctl_trunc", "truncated"), ("ctl_think", "leak")):
    rs = rows(run, "base") + rows(run, "abl")
    caught = sum(any(want in f for f in r["attempts"][0]["failures"]) for r in rs)
    passed = sum(r["first_attempt_ok"] for r in rs)
    L.append(f"- {run}: {len(rs)} rows, caught as {want}: {caught}, wrongly valid: {passed}")
    if run == "ctl_think" and rs:
        L.append(f"  - sample start: {rs[0]['attempts'][0]['text'][:160]!r}")
    gate.append((f"{run} all caught", len(rs) > 0 and passed == 0 and (caught == len(rs) or run == "ctl_think")))

L.append("\n## Gate")
L += [f"- [{'x' if ok else ' '}] {name}" for name, ok in gate]
L.append(f"\nVERDICT: {'PASS' if all(ok for _, ok in gate) else 'FAIL'}")
(OUT / "smoke_report.md").write_text("\n".join(L) + "\n")
print("\n".join(L))
