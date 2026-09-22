"""Private held-out scoring and descriptive, failure-aware pilot reports.

Mechanism recovery is exact variable/family recovery, not a causal claim or a
significance test. Predictive performance is reported separately because proxy
variables can predict well without recovering the planted variable identities.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from itertools import combinations
import json
from pathlib import Path

import numpy as np

from .data import DatasetCase


METRICS = (
    "test_mse", "kind_correct", "pair_correct", "gate_correct",
    "active_direction_correct", "mechanism_correct", "false_signal",
    "false_condition", "fit_count", "analysis_requests", "model_calls",
    "input_tokens", "output_tokens", "total_tokens", "reported_cost", "elapsed_seconds",
)
SUCCESS_STATUSES = {"success", "ok", "completed"}


def _finite_number(value):
    if value is None or isinstance(value, (str, bytes)):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if np.isfinite(number) else None


def score_submission(
    case: DatasetCase, record: dict, predictions: np.ndarray
) -> dict:
    """Score a frozen fitted record; missing/invalid predictions cannot succeed.

    ``pair_correct`` and ``gate_correct`` are null when the truth has no such
    component. For a conditional model, correct active direction means that its
    positive-side interaction slope is positive and larger than the absolute
    nonpositive-side slope. This is a descriptive direction check, not statistical
    confirmation or a confidence interval for either slope.
    """
    if predictions is None:
        raise ValueError("A failed run without predictions cannot be scored")
    predicted = np.asarray(predictions, dtype=float)
    expected = case.test["Y"].to_numpy(dtype=float)
    if predicted.ndim != 1 or predicted.shape != expected.shape:
        raise ValueError("predictions must be one-dimensional with one value per test row")
    if not np.isfinite(predicted).all() or not np.isfinite(expected).all():
        raise ValueError("test targets and predictions must be finite")
    if not isinstance(record.get("spec"), dict):
        raise ValueError("record must include a spec dictionary")
    spec = record["spec"]
    kind = spec.get("kind")
    if kind not in {"null", "linear", "interaction", "conditional"}:
        raise ValueError("Unknown submitted model kind")
    pair = spec.get("pair")
    if kind in {"interaction", "conditional"}:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2 or len(set(pair)) != 2:
            raise ValueError("An interaction model needs two distinct pair features")
        pair = sorted(pair)
    if kind == "conditional" and not isinstance(spec.get("gate"), str):
        raise ValueError("A conditional model needs a gate feature")

    truth = case.truth["spec"]
    truth_kind = truth["kind"]
    kind_correct = kind == truth_kind
    pair_correct = (
        pair == sorted(truth["pair"]) if "pair" in truth else None
    )
    gate_correct = (
        spec.get("gate") == truth["gate"] if "gate" in truth else None
    )
    active_direction_correct = None
    if truth_kind == "interaction":
        coefficient = None
        if pair is not None and kind in {"interaction", "conditional"}:
            coefficient = _finite_number(
                record.get("coefficients", {}).get("*".join(pair))
            )
        active_direction_correct = coefficient is not None and coefficient > 0
    elif truth_kind == "conditional":
        slopes = record.get("group_slopes") or {}
        positive = _finite_number(slopes.get("positive"))
        nonpositive = _finite_number(slopes.get("nonpositive"))
        active_direction_correct = (
            positive is not None and nonpositive is not None
            and positive > 0 and positive > abs(nonpositive)
        )
    mechanism_correct = bool(
        kind_correct
        and pair_correct is not False
        and gate_correct is not False
        and active_direction_correct is not False
    )
    squared_errors = np.square(predicted - expected)
    if not np.isfinite(squared_errors).all():
        raise ValueError("Prediction errors overflowed; this is not a valid score")
    return {
        "status": "success",
        "test_mse": float(np.mean(squared_errors)),
        "n_test": int(len(expected)),
        "selected_kind": kind,
        "selected_pair": pair if kind in {"interaction", "conditional"} else None,
        "selected_gate": spec.get("gate") if kind == "conditional" else None,
        "kind_correct": bool(kind_correct),
        "pair_correct": pair_correct,
        "gate_correct": gate_correct,
        "active_direction_correct": active_direction_correct,
        "mechanism_correct": mechanism_correct,
        "false_signal": bool(kind != "null") if truth_kind == "null" else None,
        "false_condition": (
            bool(kind == "conditional") if truth_kind in {"null", "interaction"}
            else None
        ),
    }


def _success(row: dict) -> bool:
    return (
        row.get("status") in SUCCESS_STATUSES
        and _finite_number(row.get("test_mse")) is not None
    )


def aggregate(rows: list[dict]) -> dict:
    """Summarize flat run rows grouped by condition and workflow.

    Required row identity: ``seed``, ``condition``, ``workflow``. Success rows
    include the score fields above; failures keep their identity and a failure
    status. MSE and correctness rates show their observed denominator; failed
    attempts are additionally included in ``mechanism_success_per_attempt``.
    Costs include failures whenever an actual cost was recorded. Paired
    differences are descriptive and only use seeds with values in both runs.
    No confidence interval or claim of low false-positive control is fabricated.
    """
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    indexed: dict[tuple[str, str, int], dict] = {}
    for row in rows:
        if not all(key in row for key in ("seed", "condition", "workflow")):
            raise ValueError("Every row must contain seed, condition, and workflow")
        identity = (row["condition"], row["workflow"], row["seed"])
        if identity in indexed:
            raise ValueError(f"Duplicate run identity: {identity}")
        indexed[identity] = row
        grouped[identity[:2]].append(row)

    score_metrics = set(METRICS[:8])
    groups = []
    for (condition, workflow), records in sorted(grouped.items()):
        successful = [row for row in records if _success(row)]
        mechanism_successes = sum(row.get("mechanism_correct") is True for row in successful)
        attempts = sum(row.get("attempt_count", 1) for row in records)
        failed_attempts = sum(row.get("failed_attempt_count", int(row.get("status") == "failed"))
                              for row in records)
        incomplete_attempts = sum(row.get("incomplete_attempt_count", int(
            row.get("status") not in SUCCESS_STATUSES | {"failed"})) for row in records)
        metrics = {}
        for metric in METRICS:
            eligible = successful if metric in score_metrics else records
            values = [
                value for row in eligible
                if (value := _finite_number(row.get(metric))) is not None
            ]
            if values:
                metrics[metric] = {
                    "mean": float(np.mean(values)),
                    "n_observed": len(values),
                    "sum": float(np.sum(values)),
                }
        groups.append({
            "condition": condition,
            "workflow": workflow,
            "n_total": len(records),
            "n_succeeded": len(successful),
            "n_failed": len(records) - len(successful),
            "n_attempts": attempts,
            "n_failed_attempts": failed_attempts,
            "n_incomplete_attempts": incomplete_attempts,
            "mechanism_successes": mechanism_successes,
            "mechanism_success_per_episode": mechanism_successes / len(records),
            "mechanism_success_per_attempt": mechanism_successes / attempts,
            "metrics": metrics,
        })

    paired = []
    for condition in sorted({key[0] for key in grouped}):
        workflows = sorted(key[1] for key in grouped if key[0] == condition)
        for workflow_a, workflow_b in combinations(workflows, 2):
            by_seed_a = {row["seed"]: row for row in grouped[(condition, workflow_a)]}
            by_seed_b = {row["seed"]: row for row in grouped[(condition, workflow_b)]}
            shared_seeds = sorted(by_seed_a.keys() & by_seed_b.keys())
            complete_seeds = [
                seed for seed in shared_seeds
                if _success(by_seed_a[seed]) and _success(by_seed_b[seed])
            ]
            for metric in METRICS:
                eligible_seeds = complete_seeds if metric in score_metrics else shared_seeds
                differences = []
                for seed in eligible_seeds:
                    a = _finite_number(by_seed_a[seed].get(metric))
                    b = _finite_number(by_seed_b[seed].get(metric))
                    if a is not None and b is not None:
                        differences.append(a - b)
                if differences:
                    paired.append({
                        "condition": condition,
                        "workflow_a": workflow_a,
                        "workflow_b": workflow_b,
                        "difference": "a_minus_b",
                        "metric": metric,
                        "mean_difference": float(np.mean(differences)),
                        "n_pairs": len(differences),
                        "n_shared_seeds": len(shared_seeds),
                        "n_both_succeeded": len(complete_seeds),
                    })
    return {
        "n_runs": len(rows),
        "groups": groups,
        "paired_differences": paired,
        "notes": [
            "Descriptive pilot results; no significance or low-error-rate claim is implied.",
            "Prediction and exact-mechanism metrics are separate; proxies may predict well.",
            "Metric denominators exclude missing values; failed attempts are shown explicitly.",
            "Paired score differences use only seeds where both workflows succeeded.",
            "Cost means include failed attempts with observed costs; missing costs are not zero.",
            "Episodes count each seed once; attempts and costs include explicitly retained retries.",
        ],
    }


def write_reports(rows: list[dict], output_dir: str | Path) -> dict:
    """Write JSON, long-form group/pair CSVs, and a compact Markdown report."""
    report = aggregate(rows)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    # The runner owns summary.json (including configuration and artifact paths).
    # A report in that same directory must never replace its run manifest.
    (output_dir / "aggregate.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n"
    )
    group_rows = []
    for group in report["groups"]:
        identity = {key: value for key, value in group.items() if key != "metrics"}
        for metric, values in group["metrics"].items():
            group_rows.append({**identity, "metric": metric, **values})
        if not group["metrics"]:
            group_rows.append({**identity, "metric": None, "mean": None, "n_observed": 0, "sum": None})
    for name, records in (("groups.csv", group_rows), ("paired.csv", report["paired_differences"])):
        with (output_dir / name).open("w", newline="") as handle:
            if records:
                writer = csv.DictWriter(handle, fieldnames=list(records[0]))
                writer.writeheader()
                writer.writerows(records)

    lines = [
        "# Adaptive analysis pilot results", "",
        "| Condition | Workflow | Episodes | Attempts | Successful episodes | Failed attempts | Test MSE (n) | Exact mechanism / attempts |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for group in report["groups"]:
        mse = group["metrics"].get("test_mse")
        mse_text = f"{mse['mean']:.5g} ({mse['n_observed']})" if mse else "unavailable (0)"
        lines.append(
            f"| {group['condition']} | {group['workflow']} | {group['n_total']} | "
            f"{group['n_attempts']} | {group['n_succeeded']} | {group['n_failed_attempts']} | {mse_text} | "
            f"{group['mechanism_successes']}/{group['n_attempts']} |"
        )
    lines += ["", "All applicable score and cost denominators are in `groups.csv`.", "",
              "## Paired differences", "",
              "Differences are workflow A minus workflow B. These are descriptive complete-pair comparisons.", "",
              "| Condition | A | B | Metric | Mean difference | Pairs / shared seeds |",
              "|---|---|---|---|---:|---:|"]
    for pair in report["paired_differences"]:
        lines.append(
            f"| {pair['condition']} | {pair['workflow_a']} | {pair['workflow_b']} | "
            f"{pair['metric']} | {pair['mean_difference']:.5g} | "
            f"{pair['n_pairs']}/{pair['n_shared_seeds']} |"
        )
    lines += ["", *[f"- {note}" for note in report["notes"]], ""]
    (output_dir / "report.md").write_text("\n".join(lines))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="A JSON list of flat run rows, or {runs: [...]}.")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text())
    rows = payload.get("runs") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        parser.error("Input must be a list or an object with a runs list")
    report = write_reports(rows, args.output_dir)
    print(json.dumps({"n_runs": report["n_runs"], "output_dir": str(args.output_dir)}))


if __name__ == "__main__":
    main()
