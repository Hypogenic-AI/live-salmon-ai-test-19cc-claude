"""
Score saved episodes: on the way from data to claim, where was the X4 X5 interaction
lost? Each step is checked against the world's own record, which the model never sees.

  1. collected  its own data contained detectable evidence (world.interaction_evidence)
  2. tested     it fitted a model with an X4:X5 term, on runs where that term could be estimated,
                or (python variant) its code formed the X4 x X5 product, or screened all pairs
                and printed a line naming X4 and X5 (those lines are listed for reading)
  3. saw        one of those fits gave X4:X5 with p < 0.05
  4. reported   its paper mentions X4 and X5 together (sentences listed, to be read by hand)
  5. predicted  its predictions on the interaction questions follow the interaction

Also: how it collected its data, and its predictions against the truth and the traps.
On questions where the true answer and the trap answer differ by more than
DISCRIMINATING_GAP, a prediction "follows" whichever of the two it is closer to.

    uv run python experiments/salmon_lab/score.py            # every episode in results/
    uv run python experiments/salmon_lab/score.py --dry-run  # the dry-run episode
"""

import argparse
import json
import re
from pathlib import Path

import numpy as np

from world import NAMES, interaction_evidence

HERE = Path(__file__).parent
RESULTS_DIR = HERE / "results"
DISCRIMINATING_GAP = 1.0
PAIR_TERMS = {"X4:X5", "X5:X4"}


def _product(a, b):
    """Code that forms the product of a and b: a:b in a formula, or a * b on columns
    (X4 * X5, df["X4"] * df["X5"], df.X4 * df.X5)."""
    closing, opening = r"""['"\]\)]*""", r"""(?:\w+\[['"]|\w+\.)?"""
    one = lambda u, v: rf"{u}\s*:\s*{v}(?!\d)|{u}{closing}\s*\*\s*{opening}{v}(?!\d)"
    return re.compile(rf"(?<![\w])(?:{one(a, b)}|{one(b, a)})")


def _feature(name):
    """X4, x4, X_4, X_{4} or X₄, but not X40."""
    digits = name[1:]
    sub = "".join("₀₁₂₃₄₅₆₇₈₉"[int(d)] for d in digits)
    return re.compile(rf"(?<![A-Za-z0-9])X_?\{{?(?:{digits}|{sub})\}}?(?![0-9])", re.I)


_X4, _X5, _X4_TIMES_X5 = _feature("X4"), _feature("X5"), _product("X4", "X5")
# Code that screens all pairs at once.
_ALL_PAIRS = re.compile(r"combinations\(|PolynomialFeatures\(|interaction_only|\([^()]*\+[^()]*\)\s*\*\*\s*2")


def _names_x4_and_x5(text):
    return bool(_X4.search(text)) and bool(_X5.search(text))


def fit_terms(request):
    formula = request.get("fit") if isinstance(request, dict) else None
    if not isinstance(formula, str) or "~" not in formula:
        return set()
    return {t.strip() for t in formula.split("~", 1)[1].split("+")}


def interaction_trail(ep):
    fits = [a for a in ep["analysis_log"] if fit_terms(a["request"]) and "coefficients" in a["result"]]
    tested = [a for a in fits if fit_terms(a["request"]) & PAIR_TERMS]
    estimates = [
        {"estimate": c["estimate"], "p": c["p"], "n": a["result"]["n"], "runs": a["result"]["runs"]}
        for a in tested for c in a["result"]["coefficients"]
        if c["term"] in PAIR_TERMS and c["estimate"] is not None
    ]
    estimated = [a for a in tested
                 if any(c["term"] in PAIR_TERMS and c["estimate"] is not None for c in a["result"]["coefficients"])]
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", ep["report"] or "") if _names_x4_and_x5(s)]
    py = python_trail(ep)
    return {
        "pair": "X4:X5",
        "collected": interaction_evidence(*_matrix(ep["rows"]))["identifiable"],
        "tested": bool(estimates) or py["tested"],
        "python": py,
        "put_x4x5_in_a_fit_it_could_not_estimate": len(estimated) < len(tested),
        "saw": any(e["p"] < 0.05 for e in estimates),
        "report_mentions_x4_with_x5": bool(sentences),
        "report_sentences": sentences,
        "x4x5_estimates_it_saw": estimates,
        "product_terms_ever_fitted": sorted({t for a in fits for t in fit_terms(a["request"]) if ":" in t}),
        "fits": len(fits),
        "analyses": len(ep["analysis_log"]),
    }


def python_trail(ep):
    blocks = [b for t in ep["turns"] for b in t.get("python", [])]
    product = [b for b in blocks if _X4_TIMES_X5.search(b["code"])]
    lines = [line.strip() for b in blocks for line in b["output"].splitlines() if _names_x4_and_x5(line)]
    screens = [b for b in blocks if _ALL_PAIRS.search(b["code"])]
    screened_and_shown = [b for b in screens if any(_names_x4_and_x5(line) for line in b["output"].splitlines())]
    return {
        "blocks": len(blocks),
        "errors": sum(b["exit_code"] != 0 and not b["timed_out"] for b in blocks),
        "timeouts": sum(b["timed_out"] for b in blocks),
        "blocks_forming_x4_times_x5": len(product),
        "blocks_screening_all_pairs": len(screens),
        "tested": bool(product or screened_and_shown),
        "output_lines_naming_x4_and_x5": lines[:12],
    }


def _matrix(rows):
    if not rows:
        return np.zeros((0, 20)), np.zeros(0)
    return np.array([r["X"] for r in rows]), np.array([r["Y"] for r in rows])


def design(ep):
    rows = ep["rows"]
    n_set = [len(r["set"]) for r in rows]
    return {
        "runs": len(rows),
        "runs_per_turn": [t.get("new_runs", 0) for t in ep["turns"]],
        "runs_nothing_set": sum(k == 0 for k in n_set),
        "runs_one_feature_set": sum(k == 1 for k in n_set),
        "runs_all_20_set": sum(k == 20 for k in n_set),
        "runs_setting_X4": sum("X4" in r["set"] for r in rows),
        "runs_setting_X5": sum("X5" in r["set"] for r in rows),
        "runs_X4_and_X5_both_set_nonzero": sum(r["set"].get("X4", 0) != 0 and r["set"].get("X5", 0) != 0 for r in rows),
        "distinct_settings": len({json.dumps(r["set"], sort_keys=True) for r in rows}),
        "features_ever_set": sorted({v for r in rows for v in r["set"]}, key=NAMES.index),
        "evidence_after_each_turn": [
            interaction_evidence(*_matrix(rows[: t["runs_so_far"]]))["identifiable"] for t in ep["turns"]
        ],
    }


def predictions(ep):
    preds = ep["predictions"] or []
    out = []
    for i, q in enumerate(ep["questions"]):
        pred = preds[i] if i < len(preds) and isinstance(preds[i], (int, float)) and not isinstance(preds[i], bool) else None
        follows = None
        if pred is not None and abs(q["true"] - q["trap"]) > DISCRIMINATING_GAP:
            follows = "trap" if abs(pred - q["trap"]) < abs(pred - q["true"]) else "true"
        out.append({"question": q["text"], "kind": q["kind"], "true": q["true"], "trap": q["trap"],
                    "predicted": pred, "abs_error": None if pred is None else round(abs(pred - q["true"]), 2),
                    "follows": follows})
    return out


def score(ep):
    preds = predictions(ep)
    follow = lambda kind: [p["follows"] for p in preds if p["kind"] == kind and p["follows"]]
    return {
        "interaction": interaction_trail(ep),
        "design": design(ep),
        "predictions": preds,
        "interaction_questions_following_truth": f"{follow('interaction').count('true')}/{len(follow('interaction'))}",
        "proxy_questions_following_truth": f"{follow('proxy').count('true')}/{len(follow('proxy'))}",
        "turns_used": len(ep["turns"]) + (1 if ep["report_turn"] else 0),
        "report_turn": ep["report_turn"],
        "report_without_tags": ep["report_without_tags"],
        "finish_reasons": [c["finish_reason"] for c in ep["calls"]],
        "cost": round(ep["cost"], 4),
    }


def show(name, s):
    i, d = s["interaction"], s["design"]
    print(f"\n===== {name} =====")
    print("{pair}:  collected {collected} | tested {tested} | saw p<0.05 {saw} | report mentions the pair "
          "{report_mentions_x4_with_x5}".format(**i))
    for e in i["x4x5_estimates_it_saw"]:
        print(f"   it fitted X4:X5 = {e['estimate']} (p = {e['p']}, runs {e['runs'][0]}-{e['runs'][1]})")
    if i["python"]["blocks"]:
        print("python: " + ", ".join(f"{k} {v}" for k, v in i["python"].items() if k != "output_lines_naming_x4_and_x5"))
        for line in i["python"]["output_lines_naming_x4_and_x5"]:
            print(f"   code output: {line[:200]}")
    for sentence in i["report_sentences"]:
        print(f"   paper: {sentence[:200]}")
    print(f"product terms it ever fitted: {i['product_terms_ever_fitted'] or 'none'}  "
          f"({i['fits']} fits, {i['analyses']} analyses)")
    print("design: " + ", ".join(f"{k} {v}" for k, v in d.items() if k != "evidence_after_each_turn"))
    print(f"evidence detectable after each turn: {d['evidence_after_each_turn']}")
    print(f"{'question':<28}{'kind':<13}{'true':>7}{'trap':>7}{'predicted':>11}  follows")
    for p in s["predictions"]:
        pred = "—" if p["predicted"] is None else f"{p['predicted']:.2f}"
        print(f"{p['question']:<28}{p['kind']:<13}{p['true']:>7.2f}{p['trap']:>7.2f}{pred:>11}  {p['follows'] or ''}")
    print(f"interaction questions following the truth: {s['interaction_questions_following_truth']}; "
          f"proxy questions: {s['proxy_questions_following_truth']}")
    print(f"turns used {s['turns_used']}, finish reasons {s['finish_reasons']}, cost ${s['cost']:.4f}")


def summary(scored):
    """One line per episode, grouped by prompt variant and model."""
    print(f"\n{'episode':<38}{'runs':>5}{'turns':>6}{'collected':>10}{'tested':>7}{'saw':>5}"
          f"{'paper':>6}{'inter.':>7}{'proxy':>6}{'products':>9}{'code':>6}{'cost':>8}")
    for name, s in scored:
        i, d = s["interaction"], s["design"]
        mark = lambda b: "yes" if b else "-"
        print(f"{name:<38}{d['runs']:>5}{s['turns_used']:>6}{mark(i['collected']):>10}{mark(i['tested']):>7}"
              f"{mark(i['saw']):>5}{mark(i['report_mentions_x4_with_x5']):>6}"
              f"{s['interaction_questions_following_truth']:>7}{s['proxy_questions_following_truth']:>6}"
              f"{len(i['product_terms_ever_fitted']):>9}{i['python']['blocks']:>6}{s['cost']:>8.2f}")
    print("paper = the paper mentions X4 and X5 in one sentence (read those sentences by hand); "
          "inter./proxy = prediction questions answered closer to the truth than to the trap; "
          "products = distinct product terms it ever fitted with the fit tool (190 possible); "
          "code = Python blocks it ran (python variant)")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="score dry_run/episode.json instead of results/")
    p.add_argument("--summary", action="store_true", help="print only the one-line-per-episode table")
    args = p.parse_args()
    paths = [HERE / "dry_run" / "episode.json"] if args.dry_run else sorted(RESULTS_DIR.glob("*/*/run*[0-9].json"))
    scored = []
    for path in paths:
        s = score(json.loads(path.read_text()))
        path.with_suffix(".score.json").write_text(json.dumps(s, indent=2))
        name = str(path.relative_to(RESULTS_DIR if not args.dry_run else HERE).with_suffix(""))
        scored.append((name, s))
        if not args.summary:
            show(name, s)
    summary(scored)


if __name__ == "__main__":
    main()
