"""Synthetic known-answer tests for the validator. Run: python3 -m pytest -q harness/ (or python3 harness/test_validate.py)"""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from validate import validate

GOOD = {"stance": "bull", "time_horizon": "1w", "thesis": "Momentum is strong and above the average.",
        "key_risks": ["Reversal after a sharp run", "Weak benchmark"],
        "confession": "The stock is far above its 50-day average, which often precedes pullbacks.",
        "reversal_trigger": "A close below 290 would make me reverse the call.", "confidence": 0.58, "p_wrong": 0.42}
G = json.dumps(GOOD)

CASES = [  # (name, text, stop, expect_ok, expected_failure_substring)
    ("good", G, "eos", True, None),
    ("good_fenced", "```json\n" + G + "\n```", "eos", True, None),
    ("empty", "", "eos", False, "empty"),
    ("whitespace", "  \n ", "eos", False, "empty"),
    ("none", None, "eos", False, "empty"),
    ("truncated_len", G[:-40], "length", False, "truncated"),
    ("truncated_but_parses", G, "length", False, "truncated"),
    ("gemma_thought_channel", "<|channel>thought\nLet me think<channel|>" + G, "eos", False, "leak"),
    ("think_tags", "<think>hmm</think>" + G, "eos", False, "leak"),
    ("reasoning_prose_prefix", "Thought: the stock rose.\n" + G, "eos", False, "text_outside_json"),
    ("turn_token", G + "<turn|>", "eos", False, "leak"),
    ("trailing_prose", G + "\nHope this helps!", "eos", False, "text_outside_json"),
    ("bad_enum", G.replace('"bull"', '"neutral"'), "eos", False, "bad_stance"),
    ("conf_out_of_range", G.replace("0.58", "1.4"), "eos", False, "bad_confidence"),
    ("conf_string", G.replace("0.58", '"0.58"'), "eos", False, "bad_confidence"),
    ("missing_field", json.dumps({k: v for k, v in GOOD.items() if k != "p_wrong"}), "eos", False, "missing"),
    ("one_risk", json.dumps({**GOOD, "key_risks": ["x"]}), "eos", False, "bad_key_risks"),
    ("empty_confession", json.dumps({**GOOD, "confession": ""}), "eos", False, "bad_confession"),
    ("array_not_object", "[1,2]", "eos", False, "not_object"),
]


def test_all():
    for name, text, stop, ok_exp, sub in CASES:
        ok, rec, fails = validate(text, stop)
        assert ok == ok_exp, (name, fails)
        if sub:
            assert any(sub in x for x in fails), (name, fails)
        else:
            assert rec["bull"] == 1 and rec["confession_words"] > 3, name


if __name__ == "__main__":
    test_all()
    print(f"{len(CASES)} validator cases passed")


def test_eos_strip_is_runner_side():
    # the validator itself must still reject a raw end-of-turn token; only the runner strips one trailing copy
    ok, _, f = validate(G + "<turn|>", "eos")
    assert not ok and any("leak" in x for x in f)
