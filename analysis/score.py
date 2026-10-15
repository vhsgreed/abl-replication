#!/usr/bin/env python3
"""Registered scorer. Implements every clause of PLAN.md section 4. One look per registered run.

  score.py out/<run>            -> prints table, writes out/<run>/score.json
  score.py --selftest           -> synthetic null + strong-effect checks of every statistic
"""
import json, pathlib, sys
import numpy as np

B = 5000
ALPHA = 1 - 0.9833                      # Bonferroni over 3 primaries in Study 1: 98.33% two-sided CIs
SEED = 20261015
MIN_PAIRED_CELLS = 400                  # NOT SCORABLE below this many cells with >=1 valid sample in BOTH arms
MAX_FAIL_RATE = 0.02                    # NOT SCORABLE if any arm's final invalid rate exceeds 2%


def load(run_dir):
    rows = []
    for f in sorted(pathlib.Path(run_dir).glob("*.jsonl")):
        rows += [json.loads(l) for l in f.open()]
    return rows


def cell_table(rows, segment=None):
    """Per (arm, cell): mean bull, mean confession words, mean confidence over valid samples.
    Paired design: keep only cells with >=1 valid sample in both arms."""
    agg = {}
    for r in rows:
        if r["split"] != "grid" or (segment and r["segment"] != segment) or not r["ok"]:
            continue
        a = agg.setdefault((r["arm"], r["cell_id"]), {"week": r["week"], "bull": [], "cw": [], "conf": []})
        res = r["result"]
        a["bull"].append(res["bull"]); a["cw"].append(res["confession_words"]); a["conf"].append(res["confidence"])
    cells = sorted({c for (_, c) in agg} & {c for (arm, c) in agg if arm == "abl"} & {c for (arm, c) in agg if arm == "base"})
    out = {"cell": cells, "week": [agg[("base", c)]["week"] for c in cells]}
    for m in ("bull", "cw", "conf"):
        for arm in ("base", "abl"):
            out[f"{m}_{arm}"] = np.array([np.mean(agg[(arm, c)][m]) for c in cells])
    return out


def cluster_boot_delta(d, weeks, seed=SEED, b=B, alpha=ALPHA):
    """Paired per-cell deltas d, bootstrap resampling WEEKS (the cluster) with replacement."""
    weeks = np.asarray(weeks)
    uw = np.unique(weeks)
    idx = {w: np.where(weeks == w)[0] for w in uw}
    rng = np.random.default_rng(seed)
    sums = np.array([d[idx[w]].sum() for w in uw]); ns = np.array([len(idx[w]) for w in uw])
    draws = rng.integers(0, len(uw), size=(b, len(uw)))
    boots = sums[draws].sum(1) / ns[draws].sum(1)
    lo, hi = np.quantile(boots, [alpha / 2, 1 - alpha / 2])
    return float(d.mean()), float(lo), float(hi)


def verdict(est, lo, hi, direction=+1):
    if direction > 0:
        return "PASS" if lo > 0 else ("OPPOSITE" if hi < 0 else "NULL")
    return "PASS" if hi < 0 else ("OPPOSITE" if lo > 0 else "NULL")


def health(rows):
    h = {}
    for arm in sorted({r["arm"] for r in rows}):
        rs = [r for r in rows if r["arm"] == arm and r["split"] == "grid"]
        fails = {}
        for r in rs:
            for a in r["attempts"]:
                for f in a["failures"]:
                    k = f.split(":")[0]
                    fails[k] = fails.get(k, 0) + 1
        h[arm] = {"n": len(rs), "first_attempt_ok": sum(r["first_attempt_ok"] for r in rs),
                  "final_ok": sum(r["ok"] for r in rs), "failure_counts": fails,
                  "render_shas": len({r["prompt_render_sha"] for r in rs})}
    return h


def score_segment(rows, seg):
    t = cell_table(rows, seg)
    n = len(t["cell"])
    res = {"segment": seg, "paired_cells": n, "weeks": len(set(t["week"]))}
    for m, name in (("bull", "H1_optimism_pp"), ("cw", "H2_confession_words"), ("conf", "X_mean_confidence")):
        d = t[f"{m}_abl"] - t[f"{m}_base"]
        if m == "bull":
            d = d * 100
        est, lo, hi = cluster_boot_delta(d, t["week"])
        res[name] = {"delta": round(est, 3), "ci": [round(lo, 3), round(hi, 3)],
                     "base_mean": round(float(t[f"{m}_base"].mean() * (100 if m == "bull" else 1)), 3),
                     "abl_mean": round(float(t[f"{m}_abl"].mean() * (100 if m == "bull" else 1)), 3),
                     "verdict": verdict(est, lo, hi) if not name.startswith("X_") else "exploratory"}
    return res


def score(run_dir):
    rows = load(run_dir)
    h = health(rows)
    scorable = all(v["n"] and (v["n"] - v["final_ok"]) / v["n"] <= MAX_FAIL_RATE for v in h.values())
    out = {"run": str(run_dir), "health": h, "ci_level": 1 - ALPHA, "bootstrap_B": B, "seed": SEED,
           "segments": {}}
    for seg in ("US", "EU"):
        s = score_segment(rows, seg)
        s["scorable"] = scorable and s["paired_cells"] >= MIN_PAIRED_CELLS
        out["segments"][seg] = s
    pathlib.Path(run_dir, "score.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    return out


def selftest():
    """Synthetic data with known answers. Null must not pass more than ~ALPHA/2 of the time (one-sided);
    a +12 pp effect at the planned n must pass in >=80% of simulations (power)."""
    rng = np.random.default_rng(1)
    weeks = np.repeat(np.arange(24), 20)                     # 24 weeks x 20 tickers per segment

    def sim(effect_pp, samples):
        wk_shift = rng.normal(0, 0.15, 24)[weeks]            # strong week-level market mood shared by both arms
        cell_shift = rng.normal(0, 0.10, len(weeks))         # cell-level shared tendency
        p_base = np.clip(0.45 + wk_shift + cell_shift, 0.02, 0.98)
        p_abl = np.clip(p_base + effect_pp / 100, 0.0, 1.0)
        base = rng.binomial(samples, p_base) / samples
        abl = rng.binomial(samples, p_abl) / samples
        return (abl - base) * 100

    for label, eff, samples, reps in (("null", 0, 3, 400), ("null", 0, 5, 400), ("effect6", 6, 3, 300),
                                      ("effect6", 6, 5, 300), ("effect12", 12, 3, 300), ("effect12", 12, 5, 300)):
        passes = 0
        for i in range(reps):
            est, lo, hi = cluster_boot_delta(sim(eff, samples), weeks, seed=i, b=1000)
            passes += lo > 0
        print(f"{label:9s} samples={samples} pass_rate={passes / reps:.3f}")


if __name__ == "__main__":
    selftest() if sys.argv[1] == "--selftest" else score(sys.argv[1])
