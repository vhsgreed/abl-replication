#!/usr/bin/env python3
"""Rebuild every article figure and the effects CSV from the scorer's JSON outputs.

Inputs are exactly the files the scorer wrote: out/grid2/score.json (Q4_K_M CPU
stack) and out/grid_bf16/score.json (BF16 GPU stack). No hypothesis value is
recomputed here; the figure script only reads them. Figures are therefore
held-out numbers throughout (the scorer's one look), except Figure 2 which
displays the per-arm means the scorer reports alongside H1 (descriptive of the
same scored data, labelled as such in the caption).

Run:  .venv/bin/python analysis/figures.py
Out:  analysis/figures/fig1_effects.{png,svg}   forest of H1/H2 estimates + CIs
      analysis/figures/fig2_bullshare.{png,svg} bull share per arm per cell
      analysis/figures/fig3_validity.{png,svg}  first-draft failures per arm/stack
      analysis/figures/effects.csv              the 8 registered estimates
"""
import csv
import json
import pathlib

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["svg.fonttype"] = "none"
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

# theme colors as constants
C_BASE = "#4a6fa5"   # base arm / Q4 stack
C_ABL = "#b85c38"    # abliterated arm / BF16 stack
C_ZERO = "#888888"
C_REF = "#2e7d32"    # original paper's estimate
C_GRID = "#dddddd"

STACKS = [("Q4 (CPU)", "out/grid2/score.json", C_BASE, "o"),
          ("BF16 (GPU)", "out/grid_bf16/score.json", C_ABL, "s")]
SEGS = ["US", "EU"]


def load():
    return {name: json.load(open(ROOT / path)) for name, path, _, _ in STACKS}


def fig1(data):
    """Headline forest: every registered estimate, CI, and the original's value."""
    fig, axes = plt.subplots(1, 2, figsize=(7.5, 3.4))
    panels = [("H1_optimism_pp", "H1  off-target optimism",
               "bull share, abl - base (percentage points)", 12.2,
               "original +12.2 pp"),
              ("H2_confession_words", "H2  verbosity",
               "confession length, abl - base (words)", 4.0,
               "original +4.0 words")]
    for ax, (key, title, xlabel, ref, reflabel) in zip(axes, panels):
        rows = []
        for stack, _, color, marker in STACKS:
            for seg in SEGS:
                d = data[stack]["segments"][seg][key]
                rows.append((f"{stack}\n{seg}", d["delta"], d["ci"], color, marker))
        for i, (label, est, ci, color, marker) in enumerate(rows):
            ax.errorbar(est, i, xerr=[[est - ci[0]], [ci[1] - est]],
                        fmt=marker, color=color, capsize=3, markersize=6,
                        label=label.replace("\n", " "))
        ax.axvline(0, color=C_ZERO, lw=1)
        ax.axvline(ref, color=C_REF, lw=1.2, ls="--")
        ax.set_yticks(range(len(rows)))
        ax.set_yticklabels([r[0].replace("\n", " ") for r in rows], fontsize=8)
        ax.set_ylim(-0.6, len(rows) - 0.2)
        ax.set_xlabel(xlabel, fontsize=8)
        ax.set_title(f"{title}\n98.33% CIs, both stacks, both segments", fontsize=9)
        ax.grid(axis="x", color=C_GRID, lw=0.6)
        ax.tick_params(labelsize=8)
        # reference label inside the axes, top, with headroom
        ax.text(ref, len(rows) - 0.45, reflabel, color=C_REF, fontsize=7,
                ha="right", va="top")
    fig.suptitle("Figure 1. Registered estimates vs the original paper's values",
                 fontsize=10, y=1.02)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, fontsize=7, ncol=4, loc="lower center",
               bbox_to_anchor=(0.5, -0.18), title="stack / segment", title_fontsize=7)
    fig.savefig(OUT / "fig1_effects.png", bbox_inches="tight", dpi=150)
    fig.savefig(OUT / "fig1_effects.svg", bbox_inches="tight")
    plt.close(fig)


def fig2(data):
    """Descriptive: bull share per arm per stack/segment (scorer-reported means)."""
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    labels, base, abl, deltas = [], [], [], []
    for stack, _, _, _ in STACKS:
        for seg in SEGS:
            d = data[stack]["segments"][seg]["H1_optimism_pp"]
            labels.append(f"{stack}\n{seg}")
            base.append(d["base_mean"])
            abl.append(d["abl_mean"])
            deltas.append(d["delta"])
    x = range(len(labels))
    w = 0.36
    ax.bar([i - w / 2 for i in x], base, w, color=C_BASE, label="base arm")
    ax.bar([i + w / 2 for i in x], abl, w, color=C_ABL, label="abliterated arm")
    for i, (b, a, dd) in enumerate(zip(base, abl, deltas)):
        ax.annotate(f"+{dd:.1f} pp", (i, max(b, a) + 1.2), ha="center", fontsize=8)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("share of bull stances (%)\nmeans over 480 paired cells", fontsize=8)
    ax.set_ylim(0, 62)
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(axis="y", color=C_GRID, lw=0.6)
    ax.tick_params(labelsize=8)
    ax.set_title("Figure 2. Bull share per arm and cell\n"
                 "descriptive of the scored data; deltas are the registered H1 values",
                 fontsize=10)
    fig.savefig(OUT / "fig2_bullshare.png", bbox_inches="tight", dpi=150)
    fig.savefig(OUT / "fig2_bullshare.svg", bbox_inches="tight")
    plt.close(fig)


def fig3(data):
    """Capability covariate: first-draft failures per arm and stack."""
    fig, ax = plt.subplots(figsize=(7.5, 3.0))
    labels, base_f, abl_f = [], [], []
    for stack, _, _, _ in STACKS:
        h = data[stack]["health"]
        labels.append(stack)
        base_f.append(2880 - h["base"]["first_attempt_ok"])
        abl_f.append(2880 - h["abl"]["first_attempt_ok"])
    x = range(len(labels))
    w = 0.36
    bars1 = ax.bar([i - w / 2 for i in x], base_f, w, color=C_BASE, label="base arm")
    bars2 = ax.bar([i + w / 2 for i in x], abl_f, w, color=C_ABL, label="abliterated arm")
    for bars in (bars1, bars2):
        for r in bars:
            ax.annotate(f"{int(r.get_height())}", (r.get_x() + r.get_width() / 2,
                        r.get_height() + 0.15), ha="center", fontsize=8)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("first-draft failures per 2,880\n(retried; all rows final-valid)", fontsize=8)
    ax.set_ylim(0, 10)
    ax.legend(fontsize=8)
    ax.grid(axis="y", color=C_GRID, lw=0.6)
    ax.tick_params(labelsize=8)
    ax.set_title("Figure 3. First-draft failures per arm and stack\n"
                 "exploratory capability covariate; asymmetry appears at 4-bit only",
                 fontsize=10)
    fig.savefig(OUT / "fig3_validity.png", bbox_inches="tight", dpi=150)
    fig.savefig(OUT / "fig3_validity.svg", bbox_inches="tight")
    plt.close(fig)


def effects_csv(data):
    with (OUT / "effects.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["stack", "segment", "hypothesis", "delta", "ci_low", "ci_high",
                    "base_mean", "abl_mean", "verdict"])
        for stack, _, _, _ in STACKS:
            for seg in SEGS:
                for key in ("H1_optimism_pp", "H2_confession_words", "X_mean_confidence"):
                    d = data[stack]["segments"][seg][key]
                    w.writerow([stack, seg, key, d["delta"], d["ci"][0], d["ci"][1],
                                d["base_mean"], d["abl_mean"], d["verdict"]])


if __name__ == "__main__":
    data = load()
    fig1(data)
    fig2(data)
    fig3(data)
    effects_csv(data)
    print("figures written to", OUT)
