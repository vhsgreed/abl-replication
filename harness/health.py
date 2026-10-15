#!/usr/bin/env python3
"""Data-health check for a run. HEALTH ONLY: per PLAN.md s4 no primary outcome (arm comparison of
stance or confession length) is computed before every cell has 3 samples in both arms.
  health.py out/<run>"""
import collections, json, pathlib, statistics as st, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
run = pathlib.Path(sys.argv[1])
arms = json.load(open(ROOT / "harness/arms.json"))
cells = {}
for l in open(ROOT / "data/cells.jsonl"):
    c = json.loads(l)
    cells[c["cell_id"]] = c
R = {a: [json.loads(l) for l in open(run / f"{a}.jsonl")] for a in ("base", "abl")}

for a, rs in R.items():
    keys = [(r["cell_id"], r["sample"]) for r in rs]
    texts = [r["attempts"][-1]["text"] for r in rs]
    ot = [r["attempts"][0]["out_tokens"] for r in rs]
    pt = [r["attempts"][0]["prompt_tokens"] for r in rs]
    ws = [r["attempts"][0]["wall_s"] for r in rs]
    ok = [r for r in rs if r["ok"]]
    print(f"\n[{a}] rows {len(rs)}, duplicate keys {len(keys) - len(set(keys))}, all grid {all(r['split'] == 'grid' for r in rs)}")
    print(f"  unknown cells {sum(r['cell_id'] not in cells for r in rs)}, model sha matches arms.json "
          f"{all(r['model_sha256'] == arms[a]['sha256'] for r in rs)}, distinct prompt/template sha "
          f"{len({r['prompt_file_sha'] for r in rs})}/{len({r['template_sha'] for r in rs})}")
    print(f"  valid {len(ok)}, first-try {sum(r['first_attempt_ok'] for r in rs)}, stop types "
          f"{dict(collections.Counter(r['attempts'][0]['stop_type'] for r in rs))}")
    print(f"  out tokens min/med/max {min(ot)}/{int(st.median(ot))}/{max(ot)}, prompt tokens {min(pt)}-{max(pt)}, "
          f"wall s median {st.median(ws):.1f}")
    print(f"  identical output texts {len(texts) - len(set(texts))}, segments "
          f"{dict(collections.Counter(r['segment'] for r in rs))}, weeks {len({r['week'] for r in rs})}, "
          f"samples {dict(collections.Counter(r['sample'] for r in rs))}")
    print(f"  field order ok {sum(r['result']['field_order_ok'] for r in ok)}/{len(ok)}, "
          f"|p_wrong-(1-conf)|>0.05: {sum(abs(r['result']['p_wrong'] - (1 - r['result']['confidence'])) > 0.05 for r in ok)}")
    print(f"  confidence values {dict(collections.Counter(r['result']['confidence'] for r in ok).most_common(5))}")

b = {(r["cell_id"], r["sample"]): r for r in R["base"]}
ab = {(r["cell_id"], r["sample"]): r for r in R["abl"]}
com = sorted(set(b) & set(ab))
print(f"\npaired {len(com)}, render-sha mismatch {sum(b[k]['prompt_render_sha'] != ab[k]['prompt_render_sha'] for k in com)}, "
      f"prompt-token mismatch {sum(b[k]['attempts'][0]['prompt_tokens'] != ab[k]['attempts'][0]['prompt_tokens'] for k in com)}, "
      f"seed mismatch {sum(b[k]['attempts'][0]['seed'] != ab[k]['attempts'][0]['seed'] for k in com)}")
print(f"cell inputs with != 10 closes: {sum(len(cells[k[0]]['last_10_closes']) != 10 for k in com)}")
