"""Render one cell into the exact prompt string sent to both arms.
We render ourselves with Google's official chat template (pinned file, hashed) and send raw text to
llama-server /completion, so neither arm depends on the template embedded in its GGUF."""
import hashlib, json, pathlib, re
import jinja2

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROMPT_FILE = ROOT / "task" / "prompt_v1.md"
TEMPLATE_FILE = ROOT / "provenance" / "google" / "chat_template.jinja"


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


PROMPT_SHA = sha(PROMPT_FILE.read_bytes())
TEMPLATE_SHA = sha(TEMPLATE_FILE.read_bytes())

_env = jinja2.Environment(extensions=["jinja2.ext.loopcontrols"])
_env.globals["raise_exception"] = lambda m: (_ for _ in ()).throw(ValueError(m))
_tpl = _env.from_string(TEMPLATE_FILE.read_text())
_sys, _usr = re.split(r"<!-- USER -->\n", PROMPT_FILE.read_text().split("<!-- SYSTEM -->\n", 1)[1])


def messages(cell):
    closes = "\n".join(f"{d}: {c}" for d, c in cell["last_10_closes"])
    return [{"role": "system", "content": _sys.strip()},
            {"role": "user", "content": _usr.strip().format(closes_block=closes, **cell)}]


def render(cell):
    """Full prompt text incl. <bos>, non-thinking mode (template inserts an empty thought channel)."""
    return _tpl.render(messages=messages(cell), bos_token="<bos>", add_generation_prompt=True, enable_thinking=False)


def load_cells(split=None):
    rows = [json.loads(l) for l in open(ROOT / "data" / "cells.jsonl")]
    return [r for r in rows if split is None or r["split"] == split]


if __name__ == "__main__":
    c = load_cells("smoke")[0]
    print(render(c))
    print("prompt_sha", PROMPT_SHA[:12], "template_sha", TEMPLATE_SHA[:12])
