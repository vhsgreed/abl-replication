"""Strict output validator. Every rule here is a smoke-test gate; nothing is repaired silently.
validate(text, stop_reason) -> (ok: bool, record: dict, failures: list[str])"""
import json, re

FIELDS = ["stance", "time_horizon", "thesis", "key_risks", "confession", "reversal_trigger", "confidence", "p_wrong"]
# Any trace of a reasoning channel or chat-control token in the visible output is a hard failure.
LEAK = re.compile(r"<\|?channel\|?>|<channel\|>|<\|think\|>|</?think>|<\|turn>|<turn\|>|<start_of_turn>|<end_of_turn>"
                  r"|^\s*thought\b|\bthinking process\b", re.I | re.M)
FENCE = re.compile(r"^\s*```(?:json)?\s*\n(.*)\n\s*```\s*$", re.S)


def words(s):
    return len(s.split())


def validate(text, stop_reason):
    f = []
    if text is None or not text.strip():
        return False, {}, ["empty"]
    if stop_reason != "eos":
        f.append(f"truncated:{stop_reason}")
    if LEAK.search(text):
        f.append("reasoning_or_control_leak")
    body, fenced = text.strip(), False
    m = FENCE.match(body)
    if m:
        body, fenced = m.group(1).strip(), True
    if not (body.startswith("{") and body.endswith("}")):
        f.append("text_outside_json")
    try:
        d = json.loads(body)
    except Exception:
        return False, {"fenced": fenced}, f + ["json_parse"]
    if not isinstance(d, dict):
        return False, {}, f + ["not_object"]
    missing = [k for k in FIELDS if k not in d]
    extra = [k for k in d if k not in FIELDS]
    if missing:
        f.append("missing:" + ",".join(missing))
    if extra:
        f.append("extra:" + ",".join(extra))
    if d.get("stance") not in ("bull", "bear"):
        f.append("bad_stance")
    if d.get("time_horizon") not in ("1w", "2w", "4w"):
        f.append("bad_horizon")
    for k in ("thesis", "confession", "reversal_trigger"):
        v = d.get(k)
        if not isinstance(v, str) or words(v) < 3:
            f.append(f"bad_{k}")
    kr = d.get("key_risks")
    if not (isinstance(kr, list) and 2 <= len(kr) <= 4 and all(isinstance(x, str) and x.strip() for x in kr)):
        f.append("bad_key_risks")
    for k in ("confidence", "p_wrong"):
        v = d.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not (0 <= v <= 1):
            f.append(f"bad_{k}")
    rec = {"fenced": fenced, "field_order_ok": list(d)[:len(FIELDS)] == FIELDS}
    if not f:
        rec.update(stance=d["stance"], bull=int(d["stance"] == "bull"), horizon=d["time_horizon"],
                   confidence=float(d["confidence"]), p_wrong=float(d["p_wrong"]),
                   confession_words=words(d["confession"]), thesis_words=words(d["thesis"]),
                   n_risks=len(kr), decision=d)
    return not f, rec, f
