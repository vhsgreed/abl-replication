#!/usr/bin/env python3
"""Overnight runner. Interleaves arms in week blocks so a run cut short by the deadline stays balanced.
Resumable: (arm, cell_id, sample) already in out/<run>/<arm>.jsonl are skipped. Every row is fsynced.

  run.py --run run1 --split grid --deadline 2026-10-16T15:50 [--samples 5] [--block-weeks 4] [--np 1]
"""
import argparse, datetime as dt, hashlib, json, os, pathlib, signal, subprocess, sys, time, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from render import render, load_cells, sha, PROMPT_SHA, TEMPLATE_SHA
from validate import validate

ROOT = pathlib.Path(__file__).resolve().parents[1]
LLAMA = pathlib.Path.home() / "src/llama.cpp/build/bin/llama-server"
ARMS = json.load(open(ROOT / "harness" / "arms.json"))          # {"base": {"gguf": ..., "sha256": ...}, "abl": {...}}
PORT = 18080
# Sampling: Gemma generation_config (temp 1.0, top_k 64, top_p 0.95) = the paper's settings.
# Every other llama.cpp sampler is pinned OFF so defaults (min_p 0.05!) cannot leak in.
SAMPLING = {"temperature": 1.0, "top_k": 64, "top_p": 0.95, "min_p": 0.0, "typical_p": 1.0,
            "repeat_penalty": 1.0, "presence_penalty": 0.0, "frequency_penalty": 0.0,
            "dry_multiplier": 0.0, "xtc_probability": 0.0, "mirostat": 0,
            "samplers": ["top_k", "top_p", "temperature"]}
N_PREDICT = 768
MAX_ATTEMPTS = 3


def seed_for(cell_id, sample, attempt):
    """Common random numbers: identical seed for both arms on the same (cell, sample, attempt)."""
    return int(hashlib.sha256(f"{cell_id}|{sample}|{attempt}".encode()).hexdigest()[:8], 16) & 0x7FFFFFFF


class Server:
    def __init__(self, np_):
        self.p, self.arm, self.np = None, None, np_

    def up(self, arm):
        if self.arm == arm:
            return
        self.down()
        log = open(ROOT / "out" / f"server_{arm}.log", "a")
        self.p = subprocess.Popen([str(LLAMA), "-m", ARMS[arm]["gguf"], "--host", "127.0.0.1", "--port", str(PORT),
                                   "-c", str(4096 * self.np), "-np", str(self.np), "-t", "8", "-tb", "16",
                                   "-sp", "--no-webui", "--seed", "0"], stdout=log, stderr=log)
        for _ in range(600):
            try:
                if json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2)).get("status") == "ok":
                    self.arm = arm
                    return
            except Exception:
                pass
            if self.p.poll() is not None:
                raise RuntimeError(f"server for {arm} exited rc={self.p.returncode}")
            time.sleep(1)
        raise RuntimeError("server did not become healthy")

    def down(self):
        if self.p and self.p.poll() is None:
            self.p.send_signal(signal.SIGTERM)
            try:
                self.p.wait(30)
            except subprocess.TimeoutExpired:
                self.p.kill()
        self.p, self.arm = None, None


def post(path, body, timeout=900):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def one(cell, sample, arm):
    prompt = render(cell)
    attempts = []
    for a in range(MAX_ATTEMPTS):
        s = seed_for(cell["cell_id"], sample, a)
        t = time.time()
        r = post("/completion", {"prompt": prompt, "n_predict": N_PREDICT, "seed": s, "cache_prompt": True, **SAMPLING})
        ok, rec, fails = validate(r.get("content"), r.get("stop_type") if not r.get("truncated") else "ctx_truncated")
        attempts.append({"attempt": a, "seed": s, "ok": ok, "failures": fails, "stop_type": r.get("stop_type"),
                         "prompt_tokens": r.get("tokens_evaluated"), "out_tokens": r.get("tokens_predicted"),
                         "wall_s": round(time.time() - t, 2), "text": r.get("content")})
        if ok:
            break
    return {"arm": arm, "cell_id": cell["cell_id"], "segment": cell["segment"], "week": cell["week"],
            "ticker": cell["ticker"], "split": cell["split"], "sample": sample,
            "prompt_render_sha": sha(prompt), "prompt_file_sha": PROMPT_SHA, "template_sha": TEMPLATE_SHA,
            "model_sha256": ARMS[arm]["sha256"], "first_attempt_ok": attempts[0]["ok"],
            "ok": attempts[-1]["ok"], "n_attempts": len(attempts), "result": rec if attempts[-1]["ok"] else None,
            "attempts": attempts, "ts": dt.datetime.now().isoformat(timespec="seconds")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--split", default="grid")
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--block-weeks", type=int, default=4)
    ap.add_argument("--np", type=int, default=1)
    ap.add_argument("--deadline", required=True)
    ap.add_argument("--cells", default=None, help="comma list of cell_ids (smoke override)")
    ap.add_argument("--arms", default="base,abl")
    a = ap.parse_args()
    deadline = dt.datetime.fromisoformat(a.deadline)
    out = ROOT / "out" / a.run
    out.mkdir(parents=True, exist_ok=True)
    arms = a.arms.split(",")
    cells = load_cells(a.split)
    if a.cells:
        keep = set(a.cells.split(","))
        cells = [c for c in cells if c["cell_id"] in keep]
    done = {arm: set() for arm in arms}
    for arm in arms:
        f = out / f"{arm}.jsonl"
        if f.exists():
            for l in f.open():
                r = json.loads(l)
                done[arm].add((r["cell_id"], r["sample"]))
    weeks = sorted({c["week"] for c in cells})
    blocks = [weeks[i:i + a.block_weeks] for i in range(0, len(weeks), a.block_weeks)]
    srv = Server(a.np)
    from concurrent.futures import ThreadPoolExecutor
    try:
        for sample in range(a.samples):                      # sample pass k completes for all cells before pass k+1
            for bi, block in enumerate(blocks):
                order = arms if (sample + bi) % 2 == 0 else arms[::-1]   # alternate which arm goes first
                for arm in order:
                    todo = [c for c in cells if c["week"] in block and (c["cell_id"], sample) not in done[arm]]
                    if not todo:
                        continue
                    if dt.datetime.now() >= deadline:
                        print("deadline reached", flush=True)
                        return
                    srv.up(arm)
                    with (out / f"{arm}.jsonl").open("a") as fh, ThreadPoolExecutor(a.np) as ex:
                        for row in ex.map(lambda c: one(c, sample, arm), todo):
                            fh.write(json.dumps(row) + "\n")
                            fh.flush()
                            os.fsync(fh.fileno())
                            done[arm].add((row["cell_id"], sample))
                            if dt.datetime.now() >= deadline:
                                break
                    print(f"{dt.datetime.now():%H:%M:%S} sample={sample} block={bi} arm={arm} n={len(todo)}", flush=True)
                    if dt.datetime.now() >= deadline:
                        print("deadline reached", flush=True)
                        return
    finally:
        srv.down()


if __name__ == "__main__":
    main()
