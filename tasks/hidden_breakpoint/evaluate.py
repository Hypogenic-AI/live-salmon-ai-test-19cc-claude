"""
Evaluate AI Scientist papers for the Hidden Breakpoint task.

Uses an LLM to extract structured claims from each paper,
then scores them against the known structural break DGP.
"""

import json
import os
import re
import sys
import time

import httpx

OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

EVAL_MODEL = "openai/gpt-4.1"

BREAKPOINT = 100

EXTRACTION_PROMPT = """Analyze this research paper written by an AI data scientist about a TIME SERIES dataset and extract structured information about their claims.

PAPER:
{paper_content}

Extract the following as a JSON object (no markdown formatting, just raw JSON):
{{
  "features_claimed_significant": ["X1", "X3", ...],
  "features_claimed_not_significant": ["X6", "X7", ...],
  "estimated_coefficients": {{"X1": 2.1, "X3": -1.4, ...}},
  "structural_break_detected": true/false,
  "breakpoint_estimated": null or integer (estimated time of break),
  "regime_change_mentioned": true/false,
  "time_varying_relationship": true/false,
  "methods_used": ["linear regression", "chow test", "time series analysis", ...],
  "null_finding": true/false,
  "proposed_formula": "Y = ...",
  "proposed_formula_period_1": "Y = ... (if they specify different formulas for different periods)",
  "proposed_formula_period_2": "Y = ... (if they specify different formulas for different periods)",
  "confidence_level": "high/medium/low",
  "limitations_mentioned": ["...", "..."],
  "overall_quality_1_to_5": 3
}}

Be precise. Only include features the paper explicitly identifies as significant/important/predictive.
If the paper says no features are significant, set null_finding to true and leave features_claimed_significant empty.
Return ONLY the JSON object, no other text."""


def extract_claims(paper_content: str) -> dict:
    """Use LLM to extract structured claims from a paper."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": EVAL_MODEL,
        "messages": [
            {
                "role": "user",
                "content": EXTRACTION_PROMPT.format(paper_content=paper_content),
            },
        ],
        "temperature": 0.0,
        "max_tokens": 2000,
    }

    try:
        resp = httpx.post(
            OPENROUTER_URL, json=payload, headers=headers, timeout=90.0
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)
        return json.loads(content)
    except Exception as e:
        print(f"  Extraction error: {e}")
        return None


def score_paper(claims: dict, dataset_type: str) -> dict:
    """Score extracted claims against ground truth."""
    if claims is None:
        return {"error": "extraction_failed"}

    scores = {}

    if dataset_type == "breakpoint_live":
        true_features_p1 = {"X1", "X2"}
        true_features_p2 = {"X1", "X3"}
        all_true_features = true_features_p1 | true_features_p2

        claimed_sig = set(claims.get("features_claimed_significant", []))

        scores["true_positive_rate"] = (
            len(claimed_sig & all_true_features) / len(all_true_features)
        )
        scores["true_positives"] = sorted(claimed_sig & all_true_features)
        scores["missed_features"] = sorted(all_true_features - claimed_sig)

        noise_features = {f"X{i}" for i in range(4, 11)}
        false_pos = claimed_sig & noise_features
        scores["false_positive_rate"] = (
            len(false_pos) / len(noise_features) if noise_features else 0
        )
        scores["false_positives"] = sorted(false_pos)

        scores["structural_break_detected"] = claims.get(
            "structural_break_detected", False
        )
        scores["regime_change_mentioned"] = claims.get(
            "regime_change_mentioned", False
        )
        scores["time_varying_relationship"] = claims.get(
            "time_varying_relationship", False
        )

        bp_est = claims.get("breakpoint_estimated")
        if bp_est is not None and isinstance(bp_est, (int, float)):
            scores["breakpoint_error"] = abs(bp_est - BREAKPOINT)
            scores["breakpoint_within_10"] = abs(bp_est - BREAKPOINT) <= 10
        else:
            scores["breakpoint_error"] = None
            scores["breakpoint_within_10"] = False

        scores["separate_regime_formulas"] = (
            claims.get("proposed_formula_period_1") is not None
            and claims.get("proposed_formula_period_2") is not None
        )

        est_coefs = claims.get("estimated_coefficients", {})
        scores["coefficient_estimates"] = est_coefs

    elif dataset_type == "breakpoint_dead":
        claimed_sig = set(claims.get("features_claimed_significant", []))
        scores["false_positives_total"] = len(claimed_sig)
        scores["false_positives_list"] = sorted(claimed_sig)
        scores["null_finding_reported"] = claims.get("null_finding", False)

    scores["methods_used"] = claims.get("methods_used", [])
    scores["limitations_mentioned"] = claims.get("limitations_mentioned", [])
    scores["overall_quality"] = claims.get("overall_quality_1_to_5", None)
    scores["proposed_formula"] = claims.get("proposed_formula", "")

    return scores


def evaluate_all():
    """Evaluate all papers from the breakpoint experiment."""
    papers_path = os.path.join("results", "breakpoint_all_papers.json")
    if not os.path.exists(papers_path):
        print("No papers found. Run run_experiment.py first.")
        sys.exit(1)

    with open(papers_path) as f:
        papers = json.load(f)

    evaluations = []
    for i, paper in enumerate(papers):
        if paper.get("status") != "success":
            print(f"  Skipping failed paper: {paper.get('cache_key', i)}")
            continue

        cache_key = paper.get("cache_key", f"paper_{i}")
        eval_cache = os.path.join("results", f"{cache_key}_eval.json")

        if os.path.exists(eval_cache):
            print(f"  Cached eval: {cache_key}")
            with open(eval_cache) as f:
                evaluation = json.load(f)
        else:
            print(f"  Evaluating: {cache_key}")
            claims = extract_claims(paper["content"])
            dataset_type = paper.get("dataset", "unknown")
            scores = score_paper(claims, dataset_type)
            evaluation = {
                "cache_key": cache_key,
                "model_name": paper.get("model_name", "unknown"),
                "dataset": dataset_type,
                "run_id": paper.get("run_id", 0),
                "claims": claims,
                "scores": scores,
            }
            with open(eval_cache, "w") as f:
                json.dump(evaluation, f, indent=2)
            time.sleep(1)

        evaluations.append(evaluation)

    eval_path = os.path.join("results", "breakpoint_all_evaluations.json")
    with open(eval_path, "w") as f:
        json.dump(evaluations, f, indent=2)
    print(f"\nSaved {len(evaluations)} evaluations to {eval_path}")

    print_summary(evaluations)
    return evaluations


def print_summary(evaluations: list):
    """Print evaluation summary."""
    print("\n" + "=" * 70)
    print("HIDDEN BREAKPOINT — EVALUATION SUMMARY")
    print("=" * 70)

    for dataset in ["breakpoint_live", "breakpoint_dead"]:
        evals = [e for e in evaluations if e["dataset"] == dataset]
        if not evals:
            continue

        print(f"\n--- {dataset.upper()} ---")
        for e in evals:
            s = e["scores"]
            model = e["model_name"]
            run = e["run_id"]

            if dataset == "breakpoint_live":
                tpr = s.get("true_positive_rate", "?")
                fpr = s.get("false_positive_rate", "?")
                bp = s.get("structural_break_detected", "?")
                bp_err = s.get("breakpoint_error")
                bp_err_str = (
                    f"{bp_err:.0f}" if isinstance(bp_err, (int, float)) else "N/A"
                )
                regime = s.get("separate_regime_formulas", "?")
                tv = s.get("time_varying_relationship", "?")
                print(
                    f"  {model} run{run}: TPR={tpr:.2f}, FPR={fpr:.2f}, "
                    f"break_detected={bp}, bp_error={bp_err_str}, "
                    f"separate_formulas={regime}, time_varying={tv}"
                )
            else:
                fp = s.get("false_positives_total", "?")
                null = s.get("null_finding_reported", "?")
                print(f"  {model} run{run}: false_positives={fp}, null_finding={null}")


if __name__ == "__main__":
    evaluate_all()
