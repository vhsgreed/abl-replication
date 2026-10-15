#!/usr/bin/env python3
"""Check both pinned HF snapshots byte-for-byte against the Hub's LFS sha256, record to provenance/weights.json.
Exit 1 on any mismatch or missing file."""
import hashlib, json, pathlib, sys, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPOS = {"google/gemma-4-26B-A4B-it": ("4d7ae4984b7db7de8f8457170b3f1a419ee76d52", "gemma-4-26B-A4B-it"),
         "huihui-ai/Huihui-gemma-4-26B-A4B-it-abliterated": ("bfa658000df7d734e0946595ab832abb7e34b1be",
                                                            "huihui-gemma-4-26B-A4B-it-abliterated")}
out, bad = {}, 0
for repo, (rev, d) in REPOS.items():
    tree = json.load(urllib.request.urlopen(f"https://huggingface.co/api/models/{repo}/tree/{rev}", timeout=30))
    for f in tree:
        if not f["path"].endswith(".safetensors"):
            continue
        p = pathlib.Path.home() / "models/hf" / d / f["path"]
        h = hashlib.sha256()
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 24), b""):
                h.update(chunk)
        want = f["lfs"]["oid"]
        ok = h.hexdigest() == want and p.stat().st_size == f["lfs"]["size"]
        bad += not ok
        out[f"{repo}@{rev}/{f['path']}"] = {"sha256": h.hexdigest(), "ok": ok}
        print(("OK  " if ok else "BAD ") + f"{repo}/{f['path']}", flush=True)
(ROOT / "provenance" / "weights.json").write_text(json.dumps(out, indent=1))
sys.exit(1 if bad else 0)
