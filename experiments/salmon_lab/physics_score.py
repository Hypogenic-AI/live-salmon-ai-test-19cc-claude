"""
Score saved physics-lab episodes, following the same steps as score.py:

  1. collected  its own runs make the colour-temperature law detectable (physics_world.interaction_evidence)
  2. tested     its code formed the product of reflectance and temperature, grouped by both,
                or screened all pairs and printed a line naming both
  3. reported   its paper mentions colour and temperature in one sentence (sentences listed)
  4. predicted  its law reproduces the new law: in held-out pairs of experiments that differ
                only in colour and temperature, the predicted difference in flight time has the
                true sign and lies within a factor of two of the true difference

An episode counts as found when step 4 passes. Steps 2 and 3 are read by pattern and checked
by hand; step 2 misses code that renames the columns.

In a world without the new law (kappa 0) step 4 asks the opposite question: whether the law
invents a colour-temperature effect, predicting in three quarters of the pairs a difference at
least half as large as the one the new law would give at its usual strength.

Also how it collected its data, how accurate its law is overall, and every sentence of
its paper that mentions a property that never matters.

    uv run python experiments/salmon_lab/physics_score.py
"""

import json
import re
from pathlib import Path

import numpy as np

import physics_world as pw
from score import _ALL_PAIRS, _product

HERE = Path(__file__).parent
RESULTS_DIR = HERE / "results" / "physics"
_PRODUCT = _product("reflectance", "temperature")
_JOINT = re.compile(r"groupby|pivot|crosstab|\bcut\(|qcut\(")
_COLOUR = re.compile(r"reflect|colou?r|dark|black|white|albedo|grey|gray", re.I)
_HEAT = re.compile(r"temperat|\bhot\b|\bcold\b|warm|heat", re.I)
_IRRELEVANT = re.compile(r"stripe|hardness|batch", re.I)


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text or "") if s.strip()]


def code_trail(ep):
    blocks = [b for t in ep["turns"] for b in t.get("python", [])]
    both = lambda line: "reflectance" in line and "temperature" in line
    formed = [b for b in blocks if _PRODUCT.search(b["code"])]
    grouped = [b for b in blocks if any(both(line) and _JOINT.search(line) for line in b["code"].splitlines())]
    shown = lambda b: any(both(line) for line in b["output"].splitlines())
    screened = [b for b in blocks if _ALL_PAIRS.search(b["code"]) and shown(b)]
    return {
        "blocks": len(blocks),
        "errors": sum(b["exit_code"] != 0 and not b["timed_out"] for b in blocks),
        "timeouts": sum(b["timed_out"] for b in blocks),
        "formed_product": len(formed),
        "grouped_by_both": len(grouped),
        "screened_and_shown": len(screened),
        "tested": bool(formed or grouped or screened),
        "output_lines_naming_both": [line.strip() for b in blocks for line in b["output"].splitlines() if both(line)][:12],
    }


def law_score(ep):
    cases, predicted = ep["law_cases"], ep["law_predictions"]
    if not predicted or len(predicted) != len(cases) or any(p is None for p in predicted):
        return {"ran": False, "failed_cases": None if not predicted else sum(p is None for p in predicted)}
    truth = pw.law_truth(cases, ep["kappa"])
    baseline = pw.law_truth(cases, 0.0)
    pred = np.array(predicted, dtype=float)
    rel = lambda a, b: np.abs(a - b) / np.maximum(np.abs(b), 1e-9)
    gap = lambda m: m[0::2, 0] - m[1::2, 0]
    errors = {
        "flight_time_error": round(float(np.median(rel(pred[:, 0], truth[:, 0]))), 4),
        "distance_error": round(float(np.median(rel(pred[:, 1], truth[:, 1]))), 4),
        "impact_speed_error": round(float(np.median(rel(pred[:, 2], truth[:, 2]))), 4),
        "baseline_flight_time_error": round(float(np.median(rel(baseline[:, 0], truth[:, 0]))), 4),
    }
    if ep["kappa"] == 0:
        hidden = np.abs(gap(pw.law_truth(cases, pw.KAPPA)))
        invented = int(np.sum(np.abs(gap(pred)) >= 0.5 * hidden))
        return {
            "ran": True,
            "pairs": len(hidden),
            "pairs_with_invented_gap": invented,
            "invents_new_law": invented >= 0.75 * len(hidden),
            "median_gap_vs_usual_law": round(float(np.median(np.abs(gap(pred)) / hidden)), 3),
            **errors,
        }
    ratio = gap(pred) / gap(truth)
    right = int(np.sum((ratio >= 0.5) & (ratio <= 2.0)))
    return {
        "ran": True,
        "pairs": len(ratio),
        "pairs_right": right,
        "captures_new_law": right >= 0.75 * len(ratio),
        "median_ratio_of_gaps": round(float(np.median(ratio)), 3),
        **errors,
    }


def design(ep):
    rows = ep["rows"]
    set_both = [r for r in rows if {"reflectance", "temperature"} <= set(r["set"]["object"])]
    return {
        "runs": len(rows),
        "runs_per_turn": [t.get("new_runs", 0) for t in ep["turns"]],
        "runs_random_object": sum(not r["set"]["object"] for r in rows),
        "runs_in_vacuum": sum(r["launch"]["air_density"] == 0 for r in rows),
        "runs_setting_reflectance_and_temperature": len(set_both),
        "runs_setting_both_away_from_neutral": sum(r["object"]["temperature"] != 20 and r["object"]["reflectance"] != 0.5
                                                   for r in set_both),
        "distinct_settings": len({json.dumps(r["set"], sort_keys=True) for r in rows}),
        "properties_ever_set": sorted({k for r in rows for k in r["set"]["object"]}, key=pw.OBJECT.index),
        "evidence_after_each_turn": [pw.interaction_evidence(rows[: t["runs_so_far"]])["identifiable"] for t in ep["turns"]],
    }


def score(ep):
    paper = sentences(ep["report"])
    code = code_trail(ep)
    law = law_score(ep)
    return {
        "collected": pw.interaction_evidence(ep["rows"]),
        "code": code,
        "report_sentences": [s for s in paper if _COLOUR.search(s) and _HEAT.search(s)],
        "irrelevant_property_sentences": [s for s in paper if _IRRELEVANT.search(s)],
        "law": law,
        "design": design(ep),
        "found": bool(law.get("captures_new_law")),
        "invented": bool(law.get("invents_new_law")),
        "turns_used": len(ep["turns"]) + (1 if ep["report_turn"] else 0),
        "finish_reasons": [c["finish_reason"] for c in ep["calls"]],
        "cost": round(ep["cost"], 4),
    }


def show(name, s):
    c, law, d = s["code"], s["law"], s["design"]
    print(f"\n===== {name} =====")
    verdict = (f"law invents it {law.get('invents_new_law')}" if "invents_new_law" in law
               else f"law captures it {law.get('captures_new_law')}")
    print(f"colour x temperature: collected {s['collected']['identifiable']} | tested {c['tested']} | "
          f"paper mentions both {bool(s['report_sentences'])} | {verdict}")
    print("code: " + ", ".join(f"{k} {v}" for k, v in c.items() if k != "output_lines_naming_both"))
    for line in c["output_lines_naming_both"]:
        print(f"   code output: {line[:200]}")
    for sentence in s["report_sentences"]:
        print(f"   paper: {sentence[:200]}")
    for sentence in s["irrelevant_property_sentences"]:
        print(f"   paper (irrelevant property): {sentence[:200]}")
    print("law: " + ", ".join(f"{k} {v}" for k, v in law.items()))
    print("design: " + ", ".join(f"{k} {v}" for k, v in d.items() if k != "evidence_after_each_turn"))
    print(f"evidence detectable after each turn: {d['evidence_after_each_turn']}")
    print(f"turns used {s['turns_used']}, finish reasons {s['finish_reasons']}, cost ${s['cost']:.4f}")


def main():
    for path in sorted(RESULTS_DIR.glob("*/*/run*[0-9].json")):
        s = score(json.loads(path.read_text()))
        path.with_suffix(".score.json").write_text(json.dumps(s, indent=2))
        show(path.relative_to(RESULTS_DIR), s)


if __name__ == "__main__":
    main()
