#!/usr/bin/env python3
"""Offline report for the Live Salmon model × prompt experiment.

Usage: python -B summarize_model_prompt_experiment.py EXPERIMENT_ROOT OUTPUT_DIR
              --repo FROZEN_SOURCE [--require-complete] [--skip-reference]

Reads raw records, including failures and retained attempts. No API, credentials,
network, or fitting. Optional min-CV scoring regenerates deterministic data and
uses saved coefficients only. Output must be outside the source repository.
Historical artifact paths are metadata; files are enumerated at their new root.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import fields
from datetime import datetime, timezone
import hashlib
import importlib
import itertools
import json
import math
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
PROFILES = ("gpt4.1", "sol_medium", "astra_medium")
PROMPTS = ("P0", "P1")
WORKFLOWS = ("fixed", "adaptive")
CONDITIONS = ("global", "conditional", "null")
FORMAL_SEEDS = tuple(range(301, 306))
DEV_SEEDS = (9010,)
TERMINAL = {"success", "failed"}
DIMENSIONS = ("profile", "prompt_variant", "workflow", "condition", "seed")
PAIR_METRICS = ("mechanism_success", "test_mse", "false_condition", "false_signal",
                "fit_count", "model_calls", "total_tokens", "reasoning_tokens",
                "reported_cost", "elapsed_seconds")


class ValidationError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise ValidationError(message)


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise ValidationError(f"Non-finite JSON: {value}")


def parse_json(raw):
    return json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique_object)


def read_json(path, hashes):
    raw = path.read_bytes()
    hashes[str(path.resolve())] = hashlib.sha256(raw).hexdigest()
    return parse_json(raw)


def compare(a, b, label):
    if isinstance(a, dict) and isinstance(b, dict):
        require(set(a) == set(b), f"Different keys: {label}")
        for key in a:
            compare(a[key], b[key], f"{label}.{key}")
    elif isinstance(a, list) and isinstance(b, list):
        require(len(a) == len(b), f"Different length: {label}")
        for index, (x, y) in enumerate(zip(a, b)):
            compare(x, y, f"{label}[{index}]")
    elif isinstance(a, bool) or isinstance(b, bool):
        require(type(a) is type(b) and a == b, f"Mismatch: {label}")
    elif finite(a) and finite(b):
        require(math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12), f"Mismatch: {label}")
    else:
        require(a == b, f"Mismatch: {label}")


def identity(record):
    config = record.get("config", {})
    return (record.get("profile", config.get("profile")),
            record.get("prompt_variant", config.get("prompt_variant")),
            record["workflow"], record["condition"], record["seed"])


def key_dict(key):
    return dict(zip(DIMENSIONS, key))


def order(key):
    return (PROFILES.index(key[0]), PROMPTS.index(key[1]),
            CONDITIONS.index(key[3]), key[4], WORKFLOWS.index(key[2]))


def mean(values):
    values = [float(v) for v in values if finite(v) or isinstance(v, bool)]
    return sum(values) / len(values) if values else None


def measure(rows, name):
    values = [row[name] for row in rows if finite(row.get(name)) or isinstance(row.get(name), bool)]
    return {"mean": mean(values), "n": len(values), "sum": sum(values) if values else None}


def attempts(record):
    return record.get("previous_attempts", []) + [record]


def event_reasoning(event):
    value = event.get("reasoning_tokens")
    if value is None:
        usage = event.get("usage")
        details = usage.get("completion_tokens_details") if isinstance(usage, dict) else None
        value = details.get("reasoning_tokens") if isinstance(details, dict) else None
    return value if finite(value) and value >= 0 else None


def extra_usage(record):
    events = [e for a in attempts(record) for e in a.get("events", []) if e.get("type") == "model_call"]
    known = [value for e in events if (value := event_reasoning(e)) is not None]
    actual = sorted({e["actual_model"] for e in events if isinstance(e.get("actual_model"), str)})
    return {"reasoning_tokens": sum(known) if len(known) == len(events) else None,
            "reasoning_tokens_partial": sum(known) if known or not events else None,
            "calls_with_reasoning_tokens": len(known),
            "actual_models": actual,
            "calls_with_actual_model": sum(isinstance(e.get("actual_model"), str) for e in events),
            "finish_reasons": dict(Counter(str(e.get("finish_reason")) for e in events)),
            "calls_with_finish_reason": sum(e.get("finish_reason") is not None for e in events)}


def validate_record(record, key, freeze, runner, prompt_registry):
    for index, attempt in enumerate(attempts(record)):
        label = f"{key}/attempt{index + 1}"
        require(identity(attempt) == key, f"Attempt identity changed: {label}")
        require(attempt.get("code_hash") == freeze["code_hash"], f"Code hash differs: {label}")
        frozen_config = {**freeze["profiles"][key[0]], "prompt_variant": key[1]}
        compare(attempt["config"], frozen_config, label + ".frozen_config")
        config = runner.Config(**attempt["config"])
        expected = runner.build_config_hash(config, seed=key[4], condition=key[3],
                                            workflow=key[2], fingerprint=attempt["data_fingerprint"],
                                            code_hash=freeze["code_hash"])
        require(expected == attempt["config_hash"], f"Configuration hash differs: {label}")
        require(attempt.get("requested_model") == attempt["config"]["model"], f"Requested model differs: {label}")
        for event in attempt.get("events", []):
            if event.get("type") != "model_call":
                continue
            require(event.get("prompt_hash") == digest({"system": event["system_prompt"], "user": event["user_prompt"]}),
                    f"Prompt hash differs: {label}")
            require(event["system_prompt"] == freeze["prompts"][key[1]], f"Call prompt differs from freeze: {label}")
            if "transport_options" in event:
                compare(event["transport_options"], runner.transport_options(config), label + ".transport_options")
            prompt_key = key[:2]
            if prompt_key in prompt_registry:
                require(prompt_registry[prompt_key] == event["system_prompt"], f"System prompt changed: {prompt_key}")
            prompt_registry[prompt_key] = event["system_prompt"]
            require(event.get("requested_model") == attempt["config"]["model"], f"Call model differs: {label}")
        if "usage" in attempt:
            compare(attempt["usage"], runner.usage_totals(attempt.get("events", [])), label + ".usage")
    if record["status"] == "success":
        selected = record.get("records", {}).get((record.get("submission") or {}).get("model_id"))
        require(isinstance(selected, dict), f"Successful episode lacks selected record: {key}")
        metrics = record.get("metrics") or {}
        require(metrics.get("status") == "success" and finite(metrics.get("test_mse")), f"Success lacks finite score: {key}")
        require(metrics.get("n_test") == 300, f"Wrong test size: {key}")
        for part in ("kind", "pair", "gate"):
            compare(metrics.get("selected_" + part), selected["spec"].get(part), f"{key}.selected_{part}")
    else:
        require(not record.get("metrics"), f"Non-success has outcome metrics: {key}")


def visible_cards(value):
    cards, evidence = {}, set()
    def walk(item):
        if isinstance(item, dict):
            if isinstance(item.get("evidence_id"), str):
                evidence.add(item["evidence_id"])
            if isinstance(item.get("model_id"), str) and isinstance(item.get("spec"), dict) and finite(item.get("cv_mse")):
                cards[item["model_id"]] = item
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
    walk(value)
    return cards, evidence


def action_name(action):
    if not isinstance(action, dict):
        return "no valid action"
    tool = action.get("tool", "unknown")
    if tool == "fit_model":
        return f"fit:{action.get('spec', {}).get('kind', '?')}"
    if tool == "diagnose":
        term = action.get("term")
        return "diagnose:" + str(action.get("mode")) + (":" + "*".join(term) if term else "")
    return tool


def compact_attempt(record, runner):
    calls = [e for e in record.get("events", []) if e.get("type") == "model_call"]
    history = []
    final_payload = {}
    final_call = next((e for e in reversed(calls) if (e.get("action") or {}).get("tool") == "submit"), None)
    if final_call is None and calls:
        final_call = calls[-1]
    if final_call and isinstance(final_call.get("user_prompt"), str):
        final_payload = parse_json(final_call["user_prompt"])
        history = final_payload.get("history", [])
    cards, evidence = visible_cards(history)
    submission = record.get("submission") or ((final_call or {}).get("action") if ((final_call or {}).get("action") or {}).get("tool") == "submit" else None)
    chosen_id = (submission or {}).get("model_id")
    chosen = cards.get(chosen_id)
    minimum = min(cards.values(), key=lambda r: (r["cv_mse"], r["model_id"])) if cards else None
    kind_best = {}
    for card in cards.values():
        kind = card["spec"]["kind"]
        if kind not in kind_best or (card["cv_mse"], card["model_id"]) < (kind_best[kind]["cv_mse"], kind_best[kind]["model_id"]):
            kind_best[kind] = card
    timeline = []
    for event in record.get("events", []):
        if event.get("type") == "model_call":
            payload = parse_json(event["user_prompt"]) if isinstance(event.get("user_prompt"), str) else {}
            timeline.append({"type": "model_call", "round": event.get("round"),
                             "action": event.get("action"), "status": event.get("status"),
                             "remaining_actions_before_call": payload.get("analysis_actions_remaining"),
                             "actual_model": event.get("actual_model"), "finish_reason": event.get("finish_reason"),
                             "reasoning_tokens": event_reasoning(event), "usage": event.get("usage"),
                             "seconds": event.get("seconds")})
        elif event.get("type") == "tool_result":
            result = event.get("result") or {}
            timeline.append({"type": "tool_result", "action": event.get("action"),
                             "result": {k: result[k] for k in ("model_id", "evidence_id", "spec", "cv_mse",
                                        "cv_mse_se", "evaluated_candidates", "candidate_counts", "group_slopes") if k in result}})
    used = [event.get("action") or {} for event in record.get("events", []) if event.get("type") == "tool_result"]
    all_actions = [event.get("action") for event in calls if event.get("action")]
    explanation = (submission or {}).get("explanation", "")
    mentions = []
    # Numeric snippets are review aids, never an automatic factuality verdict.
    for match in re.finditer(r"(?<![\w])[-+]?(?:\d+\.\d+|\d+)(?:[eE][-+]?\d+)?%?", explanation):
        mentions.append({"text": match.group(), "context": explanation[max(0, match.start()-45):match.end()+45]})
    gap = chosen["cv_mse"] - minimum["cv_mse"] if chosen and minimum else None
    citation_ids = (submission or {}).get("evidence_ids", [])
    review = {
        "submission": submission, "final_explanation": explanation,
        "selected_public_record": chosen, "minimum_exposed_cv_record": minimum,
        "selected_cv_minus_minimum_exposed": gap,
        "selection_is_minimum_exposed_cv": abs(gap) <= 1e-12 if gap is not None else None,
        "best_exposed_by_kind": kind_best,
        "exposed_model_count": len(cards), "visible_model_cards": list(cards.values()),
        "visible_evidence_ids": sorted(evidence),
        "cited_evidence_ids": citation_ids,
        "citations_not_in_final_payload": sorted(set(citation_ids) - evidence),
        "discovery_summary": final_payload.get("discovery_summary"),
        "null_seen": any(card["spec"]["kind"] == "null" for card in cards.values()),
        "pairwise_scan_completed": any(a.get("tool") == "diagnose" and a.get("mode") == "pairwise" for a in used),
        "stability_scan_completed": any(a.get("tool") == "diagnose" and a.get("mode") == "stability" for a in used),
        "fixed_exhaustive_evidence_seen": any(a.get("tool") == "fixed_evidence" for a in used),
        "remaining_actions_at_submission": final_payload.get("analysis_actions_remaining") if submission else None,
        "action_path": [action_name(a) for a in all_actions],
        "numeric_mentions_for_review": mentions,
        "review_status": "unreviewed; no automatic explanation-correctness judgment",
    }
    return {"status": record.get("status"), "failure": record.get("failure"),
            "metrics": record.get("metrics"), "costs": runner.attempt_costs(record),
            "timeline": timeline, "audit": review}


def cost_summary(rows):
    calls = sum(row.get("model_calls", 0) for row in rows)
    complete = [row for row in rows if row.get("cost_is_complete") and finite(row.get("reported_cost"))]
    known = [row["reported_cost_partial"] for row in rows if finite(row.get("reported_cost_partial"))]
    reasoning = measure(rows, "reasoning_tokens")
    known_reasoning = [row["reasoning_tokens_partial"] for row in rows if finite(row.get("reasoning_tokens_partial"))]
    return {"episodes": len(rows), "attempts": sum(row.get("attempt_count", 0) for row in rows),
            "failed_attempts": sum(row.get("failed_attempt_count", 0) for row in rows),
            "incomplete_attempts": sum(row.get("incomplete_attempt_count", 0) for row in rows),
            "model_calls": calls,
            "calls_missing_reported_cost": sum(row.get("calls_missing_reported_cost", 0) for row in rows),
            "cost_complete_episodes": len(complete),
            "reported_cost_usd": sum(row["reported_cost"] for row in complete) if len(complete) == len(rows) else None,
            "known_cost_usd": sum(known) if known else (0 if not rows else None),
            "total_tokens": measure(rows, "total_tokens"), "reasoning_tokens": reasoning,
            "reported_reasoning_tokens": reasoning["sum"] if reasoning["n"] == len(rows) else None,
            "known_reasoning_tokens": sum(known_reasoning) if known_reasoning else (0 if not rows else None),
            "calls_with_reasoning_tokens": sum(row.get("calls_with_reasoning_tokens", 0) for row in rows),
            "calls_with_actual_model": sum(row.get("calls_with_actual_model", 0) for row in rows),
            "actual_models": sorted({m for row in rows for m in row.get("actual_models", [])})}


def group_rows(rows, seeds):
    groups = []
    for profile, prompt, condition, workflow in itertools.product(PROFILES, PROMPTS, CONDITIONS, WORKFLOWS):
        selected = [r for r in rows if (r["profile"], r["prompt_variant"], r["condition"], r["workflow"]) == (profile, prompt, condition, workflow)]
        success = [r for r in selected if r["status"] == "success"]
        groups.append({"profile": profile, "prompt_variant": prompt, "condition": condition, "workflow": workflow,
                       "n_planned": len(seeds), "n_present": len(selected), "n_missing": len(seeds)-len(selected),
                       "n_success": len(success), "n_failed": sum(r["status"] == "failed" for r in selected),
                       "n_nonterminal": sum(r["status"] not in TERMINAL for r in selected),
                       "mechanism_successes": sum(r.get("mechanism_correct") is True for r in success),
                       "outcomes": {name: measure(success, name) for name in ("test_mse", "kind_correct", "pair_correct", "gate_correct", "mechanism_correct", "false_signal", "false_condition")},
                       "resources": {name: measure(selected, name) for name in PAIR_METRICS if name not in {"mechanism_success", "test_mse", "false_condition", "false_signal"}},
                       "behavior": {name: measure(success, name) for name in ("null_seen", "pairwise_scan_completed", "stability_scan_completed", "fixed_exhaustive_evidence_seen", "remaining_actions_at_submission", "selected_cv_minus_minimum_exposed", "selection_is_minimum_exposed_cv")},
                       "cost_coverage": cost_summary(selected)})
    return groups


def paired_comparisons(rows, seeds):
    indexed = {identity(row): row for row in rows}
    comparisons = []
    for contrast in ("P1_minus_P0", "adaptive_minus_fixed"):
        layouts = itertools.product(PROFILES, WORKFLOWS if contrast == "P1_minus_P0" else PROMPTS, CONDITIONS)
        for profile, fixed_dimension, condition in layouts:
            deltas = {name: [] for name in PAIR_METRICS}
            missing_pairs, nonterminal_pairs = [], []
            for seed in seeds:
                if contrast == "P1_minus_P0":
                    left, right = (profile, "P0", fixed_dimension, condition, seed), (profile, "P1", fixed_dimension, condition, seed)
                else:
                    left, right = (profile, fixed_dimension, "fixed", condition, seed), (profile, fixed_dimension, "adaptive", condition, seed)
                a, b = indexed.get(left), indexed.get(right)
                if a is None or b is None:
                    missing_pairs.append(seed)
                    continue
                if a["status"] not in TERMINAL or b["status"] not in TERMINAL:
                    nonterminal_pairs.append(seed)
                    continue
                for metric in PAIR_METRICS:
                    if metric == "mechanism_success":
                        av, bv = a["status"] == "success" and a.get("mechanism_correct") is True, b["status"] == "success" and b.get("mechanism_correct") is True
                    else:
                        if metric in {"test_mse", "false_condition", "false_signal"} and (a["status"] != "success" or b["status"] != "success"):
                            continue
                        av, bv = a.get(metric), b.get(metric)
                    if (finite(av) or isinstance(av, bool)) and (finite(bv) or isinstance(bv, bool)):
                        deltas[metric].append({"seed": seed, "left": av, "right": bv, "difference": float(bv)-float(av)})
            comparisons.append({"contrast": contrast, "profile": profile, "condition": condition,
                                "workflow" if contrast == "P1_minus_P0" else "prompt_variant": fixed_dimension,
                                "n_planned_pairs": len(seeds), "missing_pair_seeds": missing_pairs,
                                "nonterminal_pair_seeds": nonterminal_pairs,
                                "metrics": {name: {"n_pairs": len(vals), "mean_difference": mean(v["difference"] for v in vals), "pairs": vals} for name, vals in deltas.items()}})
    return comparisons


def mincv_record(record):
    # A failed run may stop during the fixed search. Partial candidates are not
    # the exhaustive reference, even if an intercept or linear fit was saved.
    completed_fixed = any(e.get("type") == "tool_result" and (e.get("action") or {}).get("tool") == "fixed_evidence"
                          for e in record.get("events", []))
    if not completed_fixed:
        return None
    ids = record.get("exposed_model_ids", [])
    models = record.get("records", {})
    candidates = [models[mid] for mid in ids if mid in models and finite(models[mid].get("cv_mse"))]
    require(len(models) == 3612, "Completed fixed evidence lacks all 3,612 candidate records")
    require(bool(candidates), "Completed fixed evidence exposes no candidates")
    chosen = min(candidates, key=lambda r: (r["cv_mse"], r["model_id"]))
    all_minimum = min(models.values(), key=lambda r: (r["cv_mse"], r["model_id"]))
    compare(chosen, all_minimum, "Exposed fixed minimum differs from exhaustive minimum")
    return chosen


def reference_scores(reference_inputs, repo, skip):
    if skip:
        return {"status": "skipped", "reason": "--skip-reference", "rows": []}
    import numpy as np
    data = importlib.import_module("experiments.adaptive_analysis.data")
    evaluator = importlib.import_module("experiments.adaptive_analysis.evaluate")
    rows = []
    for (stage, seed, condition), item in sorted(reference_inputs.items()):
        config = item["config"]
        case = data.make_case(seed, condition, n_samples=config["n_samples"], n_discovery=config["n_discovery"])
        require(case.fingerprint == item["fingerprint"], f"Regenerated data fingerprint differs: {stage}/{seed}/{condition}")
        chosen = item["record"]
        spec, coefs = chosen["spec"], chosen["coefficients"]
        X = case.test.drop(columns=["Y"])
        predictions = np.full(len(X), coefs["intercept"], dtype=float)
        if spec["kind"] != "null":
            for column in X:
                predictions += X[column].to_numpy() * coefs[column]
        if "pair" in spec:
            pair_name = "*".join(spec["pair"])
            product = X[spec["pair"][0]].to_numpy() * X[spec["pair"][1]].to_numpy()
            predictions += product * coefs[pair_name]
            if spec["kind"] == "conditional":
                predictions += product * (X[spec["gate"]].to_numpy() > 0) * coefs[f"{pair_name}|{spec['gate']}>0"]
        rows.append({"stage": stage, "seed": seed, "condition": condition,
                     "spec": spec, "model_id": chosen["model_id"], "cv_mse": chosen["cv_mse"],
                     "fixed_records_verified": item["count"], "source_artifacts": item["sources"],
                     **evaluator.score_submission(case, chosen, predictions)})
    return {"status": "computed_from_saved_coefficients", "fitted_models": 0,
            "rule": "Minimum exposed discovery CV MSE in fixed evidence; ties by model_id. Deduplicated across model/prompt cells.",
            "rows": rows}


def load_stage(root, stage, seeds, freeze, runner, hashes, prompt_registry, references):
    expected = set(itertools.product(PROFILES, PROMPTS, WORKFLOWS, CONDITIONS, seeds))
    rows, trajectories, summaries, seen = [], [], [], {}
    stage_dir = root / stage
    if not stage_dir.exists():
        return {"rows": [], "trajectories": [], "missing": [key_dict(k) for k in sorted(expected, key=order)],
                "groups": group_rows([], seeds), "summary_rows_checked": 0, "progress_rows_checked": 0,
                "cost_coverage": cost_summary([])}
    for path in sorted(stage_dir.rglob("*.json")):
        require(path.resolve().is_relative_to(stage_dir.resolve()), f"Archive symlink outside stage: {path}")
        obj = read_json(path, hashes)
        if isinstance(obj, dict) and "runs" in obj and "plan" in obj:
            summaries.append((path, obj))
            continue
        if not isinstance(obj, dict) or not {"config_hash", "config", "seed", "condition", "workflow", "events"}.issubset(obj):
            continue
        key = identity(obj)
        require(key in expected, f"Unexpected episode identity in {path}: {key}")
        require(key not in seen, f"Duplicate episode identity: {key}; files {seen.get(key)} and {path}")
        validate_record(obj, key, freeze, runner, prompt_registry)
        original_flat = runner.flatten_episode(obj)
        compact = [compact_attempt(a, runner) for a in attempts(obj)]
        audit = compact[-1]["audit"]
        row = {**original_flat, **key_dict(key), **extra_usage(obj), "data_fingerprint": obj["data_fingerprint"],
               "artifact": str(path.relative_to(root)), "failure": obj.get("failure"),
               **{name: audit[name] for name in ("null_seen", "pairwise_scan_completed", "stability_scan_completed", "fixed_exhaustive_evidence_seen", "remaining_actions_at_submission", "selected_cv_minus_minimum_exposed", "selection_is_minimum_exposed_cv")}}
        rows.append(row)
        seen[key] = {"path": str(path), "flat": original_flat,
                     "record_fields": {field: obj.get(field) for field in ("status", "failure", "usage")}}
        trajectories.append({**key_dict(key), "stage": stage, "artifact": str(path.relative_to(root)), "row": row, "attempts": compact})
        if key[2] == "fixed":
            chosen = mincv_record(obj)
            if chosen is not None:
                reference_key = (stage, key[4], key[3])
                comparison = {"record": chosen, "fingerprint": obj["data_fingerprint"]}
                if reference_key in references:
                    previous = references[reference_key]
                    compare(comparison, {"record": previous["record"], "fingerprint": previous["fingerprint"]}, f"Fixed min-CV reference differs: {reference_key}")
                    previous["count"] += 1
                    previous["sources"].append(str(path.relative_to(root)))
                else:
                    references[reference_key] = {**comparison, "config": obj["config"], "count": 1, "sources": [str(path.relative_to(root))]}
    # Raw files are the ledger. Summaries may lag an interrupted run; every listed
    # row must nevertheless agree with the corresponding raw flattening.
    summary_rows_checked = 0
    for path, summary in summaries:
        summary_seen = set()
        for flat in summary.get("runs", []):
            key = identity(flat)
            if key[:2] == (None, None):
                cfg = summary.get("plan", {}).get("config", {})
                key = (cfg.get("profile"), cfg.get("prompt_variant"), *key[2:])
            require(key not in summary_seen, f"Duplicate row in summary: {path}/{key}")
            summary_seen.add(key)
            require(key in seen, f"Summary lists absent raw episode: {path}/{key}")
            compare(flat, seen[key]["flat"], f"Summary/raw mismatch: {path}/{key}")
            summary_rows_checked += 1
    progress_rows_checked = 0
    progress_path = root / (stage + "-progress.json")
    if progress_path.is_file():
        progress = read_json(progress_path, hashes)
        require(progress.get("planned") == len(expected), f"Progress plan differs: {stage}")
        progress_seen = set()
        for entry in progress.get("completed", []):
            seed, condition, profile, variant, workflow = entry["job"]
            key = (profile, variant, workflow, condition, seed)
            require(key in seen and key not in progress_seen, f"Missing or duplicate progress/raw identity: {key}")
            progress_seen.add(key)
            require(Path(entry["path"]).name == Path(seen[key]["path"]).name, f"Progress/raw artifact basename differs: {key}")
            for field in ("status", "failure", "usage"):
                compare(entry.get(field), seen[key]["record_fields"][field], f"Progress/raw mismatch: {key}/{field}")
            progress_rows_checked += 1
    rows.sort(key=lambda row: order(identity(row)))
    trajectories.sort(key=lambda row: order(identity(row)))
    return {"rows": rows, "trajectories": trajectories,
            "missing": [key_dict(k) for k in sorted(expected-set(seen), key=order)],
            "groups": group_rows(rows, seeds), "cost_coverage": cost_summary(rows),
            "summary_rows_checked": summary_rows_checked, "progress_rows_checked": progress_rows_checked}


def number(value, digits=5):
    return f"{value:.{digits}f}" if finite(value) else "NA"


def metric_text(item):
    return f"{number(item['mean'])} (n={item['n']})"


def table(headers, rows):
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"] + ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows])


def outcome_table(groups):
    return table(["Profile", "Prompt", "Data", "Workflow", "Completed / planned", "Exact structure / planned", "Test MSE (n)", "False condition (n)", "False signal (n)", "Failed / nonterminal / missing"],
                 [[g["profile"], g["prompt_variant"], g["condition"], g["workflow"], f"{g['n_success']}/{g['n_planned']}", f"{g['mechanism_successes']}/{g['n_planned']}", metric_text(g["outcomes"]["test_mse"]), metric_text(g["outcomes"]["false_condition"]), metric_text(g["outcomes"]["false_signal"]), f"{g['n_failed']}/{g['n_nonterminal']}/{g['n_missing']}"] for g in groups])


def resource_table(groups):
    rows = []
    for g in groups:
        c = g["cost_coverage"]
        money = number(c["reported_cost_usd"], 6) if c["reported_cost_usd"] is not None else ">=" + number(c["known_cost_usd"], 6) + " known"
        reasoning = (number(c["reported_reasoning_tokens"], 0) if c["reported_reasoning_tokens"] is not None
                     else ">=" + number(c["known_reasoning_tokens"], 0) + " known")
        rows.append([g["profile"], g["prompt_variant"], g["condition"], g["workflow"], metric_text(g["resources"]["fit_count"]), metric_text(g["resources"]["model_calls"]), f"{money}; {c['cost_complete_episodes']}/{c['episodes']} episodes, {c['model_calls']-c['calls_missing_reported_cost']}/{c['model_calls']} calls", f"{c['total_tokens']['sum']} ({c['total_tokens']['n']}/{c['episodes']})", f"{reasoning} ({c['calls_with_reasoning_tokens']}/{c['model_calls']} calls; {c['reasoning_tokens']['n']}/{c['episodes']} complete episodes)", metric_text(g["resources"]["elapsed_seconds"]), c["failed_attempts"]])
    return table(["Profile", "Prompt", "Data", "Workflow", "Mean fits (n)", "Mean calls (n)", "USD / coverage", "Tokens / episode coverage", "Reasoning tokens / known coverage", "Mean seconds (n)", "Failed attempts"], rows)


def pair_table(pairs):
    return table(["Contrast (right − left)", "Profile", "Other factor", "Data", "Δ structure (n)", "Δ MSE (n)", "Δ fits (n)", "Δ calls (n)", "Δ USD (n)"],
                 [[p["contrast"], p["profile"], p.get("workflow", p.get("prompt_variant")), p["condition"], *[f"{number(p['metrics'][name]['mean_difference'])} ({p['metrics'][name]['n_pairs']})" for name in ("mechanism_success", "test_mse", "fit_count", "model_calls", "reported_cost")]] for p in pairs])


def behavior_table(groups):
    fields = ("null_seen", "pairwise_scan_completed", "stability_scan_completed", "fixed_exhaustive_evidence_seen", "remaining_actions_at_submission", "selected_cv_minus_minimum_exposed")
    return table(["Profile", "Prompt", "Data", "Workflow", "Null seen (n)", "Pairwise used (n)", "Stability used (n)", "Fixed search seen (n)", "Remaining actions (n)", "Selected CV − best visible (n)"],
                 [[g["profile"], g["prompt_variant"], g["condition"], g["workflow"], *[metric_text(g["behavior"][field]) for field in fields]] for g in groups])


def reference_table(reference):
    if reference["status"] == "skipped":
        return "Reference scoring was explicitly skipped."
    rows = []
    for condition in CONDITIONS:
        subset = [r for r in reference["rows"] if r["stage"] == "formal" and r["condition"] == condition]
        rows.append([condition, f"{sum(r['mechanism_correct'] is True for r in subset)}/{len(subset)}", metric_text(measure(subset, "test_mse")), metric_text(measure(subset, "false_condition")), metric_text(measure(subset, "false_signal"))])
    return table(["Data", "Exact structure / available", "Test MSE (n)", "False condition (n)", "False signal (n)"], rows)


def quote(text):
    return "\n".join("> " + line for line in (text or "[No submitted explanation]").splitlines())


def trajectories_text(stages):
    lines = ["# All recorded trajectories", "", "Every raw episode and retained attempt is included. Development is separate. Missing episodes are listed in metrics.json. Model explanations are quoted evidence, not endorsed conclusions. Remaining actions come from the actual pre-call payload.", ""]
    for stage, data in stages.items():
        for trajectory in data["trajectories"]:
            label = " / ".join(str(trajectory[k]) for k in DIMENSIONS)
            lines += [f"## {stage} / {label}", "", f"Artifact: `{trajectory['artifact']}`", ""]
            for index, attempt in enumerate(trajectory["attempts"], 1):
                lines += [f"### Attempt {index}: {attempt['status']}", "", f"Failure: `{canonical(attempt['failure'])}`", "", f"Costs: `{canonical(attempt['costs'])}`", ""]
                for event in attempt["timeline"]:
                    if event["type"] == "model_call":
                        lines.append(f"- Call {event['round']}, {event['status']}, remaining={event['remaining_actions_before_call']}: `{canonical(event['action'])}`; actual_model={event['actual_model']}, finish={event['finish_reason']}, reasoning_tokens={event['reasoning_tokens']}.")
                    else:
                        lines.append(f"- Tool `{action_name(event['action'])}` → `{canonical(event['result'])}`")
                lines += ["", quote(attempt["audit"]["final_explanation"]), "", f"Hidden scores after submission: `{canonical(attempt['metrics'])}`", ""]
    return "\n".join(lines)


def audit_rows(stages):
    rows = []
    for stage, data in stages.items():
        for trajectory in data["trajectories"]:
            for index, attempt in enumerate(trajectory["attempts"], 1):
                rows.append({"stage": stage, **{k: trajectory[k] for k in DIMENSIONS},
                             "artifact": trajectory["artifact"], "attempt": index,
                             "status": attempt["status"], "failure": attempt["failure"],
                             "postsubmission_metrics": attempt["metrics"], **attempt["audit"]})
    return rows


def audit_text(audits):
    lines = ["# Final-explanation evidence audit", "", "This reporting script produces unreviewed evidence packets for every attempt, including failed and unfinished runs; it does not judge explanation correctness. Primary outcome metrics are deterministic. Separate assistant-assisted evidence review, when provided, is in EXPLANATION_REVIEW.md/json and is not part of the primary score. JSONL includes all public candidate cards and the discovery summary actually visible at the final call. Hidden scores are isolated as post-submission outcomes, never evidence available to the model.", "", "Review each explanation for: (1) claims supported by the visible numbers; (2) accurate scope of performed scans; (3) calibrated treatment of CV selection and uncertainty; (4) an explicit reason for any non-minimum-CV selection. A higher CV score may reflect a justified simplicity choice and is not automatically an error. An unused action budget or omitted scan is behavioral evidence, not proof that the model should have spent more.", ""]
    lines.append(table(["Stage", "Profile / prompt / workflow", "Data / seed / attempt", "Status", "Null seen", "Pairwise / stability", "Actions left", "CV gap", "Unseen citations", "Review"],
                       [[r["stage"], f"{r['profile']} / {r['prompt_variant']} / {r['workflow']}", f"{r['condition']} / {r['seed']} / {r['attempt']}", r["status"], r["null_seen"], f"{r['pairwise_scan_completed']} / {r['stability_scan_completed']}", r["remaining_actions_at_submission"], number(r["selected_cv_minus_minimum_exposed"]), ", ".join(r["citations_not_in_final_payload"]) or "none", "unreviewed"] for r in audits]))
    for row in audits:
        label = " / ".join(str(row[k]) for k in ("stage", *DIMENSIONS, "attempt"))
        values = {"selected": row["selected_public_record"], "minimum_visible": row["minimum_exposed_cv_record"], "best_by_kind": row["best_exposed_by_kind"], "cited_evidence": row["cited_evidence_ids"], "numeric_mentions": row["numeric_mentions_for_review"]}
        lines += ["", f"## {label}", "", quote(row["final_explanation"]), "", "```json", json.dumps(values, ensure_ascii=False, indent=2), "```"]
    return "\n".join(lines) + "\n"


def write_reports(root, output, repo, complete, skip_reference):
    hashes, prompts, references = {}, {}, {}
    freeze = read_json(root / "freeze.json", hashes)
    require(set(freeze["profiles"]) == set(PROFILES), "Frozen profiles differ from the planned matrix")
    require(set(freeze["prompt_variants"]) == set(PROMPTS), "Frozen prompt variants differ")
    require(set(freeze["conditions"]) == set(CONDITIONS) and set(freeze["workflows"]) == set(WORKFLOWS), "Frozen conditions/workflows differ")
    require(freeze["seeds"] == list(FORMAL_SEEDS) and freeze["development_seed"] == DEV_SEEDS[0], "Frozen seeds differ")
    for stage, seeds in (("formal", FORMAL_SEEDS), ("development", DEV_SEEDS)):
        expected_schedule = set(itertools.product(seeds, CONDITIONS, PROFILES, PROMPTS, WORKFLOWS))
        schedule = [tuple(row) for row in freeze[stage + "_schedule"]]
        require(len(schedule) == len(expected_schedule) and set(schedule) == expected_schedule,
                f"Frozen {stage} schedule is incomplete or duplicated")
        require(freeze[stage + "_episode_count"] == len(expected_schedule), f"Frozen {stage} episode count differs")
    sys.path.insert(0, str(repo))
    runner = importlib.import_module("experiments.adaptive_analysis.run")
    require({"profile", "prompt_variant"}.issubset({f.name for f in fields(runner.Config)}), "Source Config lacks model/prompt fields")
    require(runner.code_fingerprint() == freeze["code_hash"], "Source code does not match freeze")
    for variant in PROMPTS:
        require(runner.system_prompt(variant) == freeze["prompts"][variant], f"Frozen {variant} prompt differs from source")
    stages = {"development": load_stage(root, "development", DEV_SEEDS, freeze, runner, hashes, prompts, references),
              "formal": load_stage(root, "formal", FORMAL_SEEDS, freeze, runner, hashes, prompts, references)}
    all_rows = [r for stage in stages.values() for r in stage["rows"]]
    fingerprints = {}
    for row in all_rows:
        key = (row["seed"], row["condition"])
        if key in fingerprints:
            require(fingerprints[key] == row["data_fingerprint"], f"Data pairing failed: {key}")
        fingerprints[key] = row["data_fingerprint"]
    # Within each prompt variant, profiles receive identical instructions.
    for variant in PROMPTS:
        texts = {value for (profile, p), value in prompts.items() if p == variant}
        require(len(texts) <= 1, f"System prompt differs across profiles for {variant}")
    is_complete = all(not stage["missing"] and all(r["status"] in TERMINAL for r in stage["rows"]) for stage in stages.values())
    if complete:
        require(is_complete, "Experiment lacks all 180 formal + 36 development terminal records")
    reference = reference_scores(references, repo, skip_reference)
    formal = stages["formal"]
    pairs = paired_comparisons(formal["rows"], FORMAL_SEEDS)
    audits = audit_rows(stages)
    validation = {"raw_records_enumerated": True, "configuration_and_code_hashes_matched": True,
                  "prompt_hashes_matched": True,
                  "summary_rows_checked": sum(stage["summary_rows_checked"] for stage in stages.values()),
                  "progress_rows_checked": sum(stage["progress_rows_checked"] for stage in stages.values()),
                  "data_fingerprints_paired": True, "statistical_models_refitted": 0,
                  "model_calls_by_reporter": 0, "all_planned_records_terminal": is_complete,
                  "mincv_heldout_scored_from_saved_coefficients": not skip_reference}
    metrics = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
               "status": "complete" if is_complete else "provisional_incomplete",
               "freeze": freeze, "validation": validation,
               "plan": {"profiles": PROFILES, "prompt_variants": PROMPTS, "workflows": WORKFLOWS,
                        "conditions": CONDITIONS, "formal_seeds": FORMAL_SEEDS, "development_seeds": DEV_SEEDS},
               "stages": {name: {k: v for k, v in stage.items() if k != "trajectories"} for name, stage in stages.items()},
               "paired_comparisons": pairs, "mincv_reference": reference,
               "all_spending": cost_summary(all_rows), "system_prompts": {f"{p}/{v}": text for (p,v), text in prompts.items()},
               "source_sha256": hashes}
    stage_costs = table(["Stage", "Present / planned", "Calls", "USD", "Known USD", "Cost complete episodes", "Failed attempts"],
                       [[name, f"{len(stage['rows'])}/{36 if name == 'development' else 180}", cost_summary(stage["rows"])["model_calls"], number(cost_summary(stage["rows"])["reported_cost_usd"], 6), number(cost_summary(stage["rows"])["known_cost_usd"], 6), f"{cost_summary(stage['rows'])['cost_complete_episodes']}/{len(stage['rows'])}", cost_summary(stage["rows"])["failed_attempts"]] for name, stage in stages.items()])
    provider_table = table(["Profile", "Requested models", "Observed actual models", "Actual-model coverage"],
                           [[profile, ", ".join(sorted({r["requested_model"] for r in all_rows if r["profile"] == profile})), ", ".join(cost_summary([r for r in all_rows if r["profile"] == profile])["actual_models"]) or "unknown", f"{cost_summary([r for r in all_rows if r['profile'] == profile])['calls_with_actual_model']}/{cost_summary([r for r in all_rows if r['profile'] == profile])['model_calls']} calls"] for profile in PROFILES])
    report = f"""# Model × prompt Live Salmon experiment

Status: **{metrics['status']}**. Formal records: {len(formal['rows'])}/180. Development records: {len(stages['development']['rows'])}/36. Missing configurations remain visible in every table and metrics.json.

The planned factorial comparison uses three model profiles, P0/P1 instructions, fixed/adaptive workflows, global/conditional/null data, and formal seeds 301–305. Development seed 9010 is separate. Exact frozen prompts and transport settings are retained in freeze and metrics.json. Do not pool this experiment with the earlier GPT-4.1 pilot.

Each episode uses 1,000 rows, 700 discovery rows, 300 hidden test rows, and five-fold discovery CV. The conditional term is sqrt(2) × 0.8 × X4 × X5 × I(X6 > 0), with seed-specific anonymization. A uses exhaustive fixed evidence followed by one model selection; B adaptively selects analysis tools with up to eight analysis actions. Shared tools do not imply equal evidence volume, model calls, or computation. These compare workflows, not an isolated causal effect of feedback.

## Model identity

{provider_table}

Returned model names are provider metadata, not proof of a particular immutable backend revision. Missing actual-model, finish-reason, reasoning-token, and billing fields remain unknown. Requested reasoning effort is a configuration, while reported reasoning tokens describe usage when available.

## Formal outcomes

{outcome_table(formal['groups'])}

Exact-structure success includes the existing direction check; it does not establish causality or recover all main-effect coefficients. Planned denominators include failures; missing records make this report provisional. MSE and false-selection means use successful applicable episodes only, with explicit n. False condition applies to global/null, false signal to null. These are model-selection frequencies, not calibrated statistical test error rates. Five seeds per cell support descriptive comparison, not a general ranking of models or significance claims.

## Formal resources

{resource_table(formal['groups'])}

All retained attempts contribute resource costs. A scan consumes one analysis action but its full internal fits are counted. Missing provider costs are not zero; partial known sums and episode/call coverage are explicit. Interrupted work may have unpersisted time or fits. Reasoning tokens may be a subset of completion tokens and must not be added to total tokens.

## Paired changes

{pair_table(pairs)}

All signs are explicit: P1 − P0 and adaptive − fixed. Structure deltas use pairs with two terminal records, counting execution failures as no success; MSE/false-selection deltas require both episodes to complete successfully. Cost deltas retain failed-attempt costs and require known values. Missing pairs are omitted and listed by seed in metrics.json. These contrasts describe this small sample; model/prompt/strategy interactions prevent collapsing everything into one winner.

## Selection behavior

{behavior_table(formal['groups'])}

These behavioral means use successful episodes. Raw paths and failed attempts remain in TRAJECTORIES.md. Fixed evidence includes both exhaustive scans without calling diagnose, so its zero diagnose count does not mean the evidence was unavailable. Null seen refers to an exposed fitted null candidate, not a verbal mention. Selected CV minus minimum exposed CV is descriptive: simpler-model preferences can be defensible, and this gap is not an automatic error label. Remaining actions alone do not show wasted budget.

## Deterministic min-CV reference

{reference_table(reference)}

The auxiliary rule selects the minimum discovery-CV candidate already exposed by the fixed workflow, breaking ties by model ID. It is deduplicated across profiles/prompts for each seed and condition; reference scores use saved coefficients on regenerated matching held-out data, with no refitting. This reference is separate from the randomized model/prompt cells and has no incremental API cost. Coverage and repeated fixed-record consistency checks are in metrics.json.

## Spending ledger

{stage_costs}

Total reported cost for this experiment: {number(metrics['all_spending']['reported_cost_usd'], 6)} USD; known partial sum: {number(metrics['all_spending']['known_cost_usd'], 6)} USD. Development costs are separate from primary outcomes. Prior pilots and superseded interface trials are outside this experiment's ledger.

## Explanation evidence audit

EXPLANATION_AUDIT.jsonl retains all final explanation text, public candidate cards, null/linear/each-family minima, numerical snippets, citations, actual final discovery summary, performed scan flags, and remaining budget. EXPLANATION_AUDIT.md provides a review index and compact evidence packets. Primary outcome metrics are deterministic. This reporting script does not judge explanations; separate assistant-assisted evidence review, when provided, is in EXPLANATION_REVIEW.md/json and is not part of the primary score. Numeric mentions and non-minimum-CV choices require review against the supplied evidence. All cases are included, not only successful or interesting ones.

Source hashes, configuration/prompt checks, missing cells, paired seed-level differences, and provider coverage are in metrics.json. Raw records are authoritative. Optional inventory reconciliation checked {validation['progress_rows_checked']} progress rows and {validation['summary_rows_checked']} summary rows; absent summaries are not claimed to have been checked. Historical absolute paths were not rewritten; the archive is read from its current location. No APIs or fitting were used by this reporter.
"""
    chinese = f"""# 模型 × 提示规则实验摘要

状态：**{metrics['status']}**。正式记录 {len(formal['rows'])}/180，开发记录 {len(stages['development']['rows'])}/36。以下描述本地实验；缺失或未终结记录不会被视为成功。

三个 profile × P0/P1 × 固定/自适应 × global/conditional/null，正式 seeds 301–305，每格 5 个；开发 seed 9010 单列。冻结配置和提示原文保留在 metrics.json。与此前 pilot 不合并。

## 正式结果

{outcome_table(formal['groups'])}

成功列使用计划 episode 数作分母；MSE 与误选仅统计成功完成且适用的样本。结构正确包含既定方向检查，不代表证明因果关系或恢复所有系数。误选频率不是已校准的显著性检验误报率。每格只有 5 个 seed，不据此宣称模型的普遍优劣。

## 配对差

{pair_table(pairs)}

方向固定为 P1−P0、adaptive−fixed；不翻转 A/B。结构成功差将执行失败计为未成功，MSE 要求两边均完成；缺失配对和每个 seed 的差值见 metrics.json。不同流程的证据量、调用次数及计算量不同，不将差异归因于单一反馈机制。

## 费用

{stage_costs}

本批完整已报告费用 {number(metrics['all_spending']['reported_cost_usd'], 6)} 美元，已知部分 {number(metrics['all_spending']['known_cost_usd'], 6)} 美元；未知项不填零。保留失败尝试、开发集费用及各项 coverage。旧 pilot 费用不在此账本。

行为表、逐例行动和剩余预算见 REPORT.md / TRAJECTORIES.md；所有最终解释及当时可见证据见 EXPLANATION_AUDIT.jsonl / .md。主指标采用确定性评分；此脚本只整理证据，不判定解释正确性。另行提供的助手辅助证据审查见 EXPLANATION_REVIEW.md/json，不参与主评分。选择非最低 CV 模型不自动判错。辅助 min-CV 规则只用保存系数离线评分，不重新拟合，也不请求模型。
"""
    outputs = {"REPORT.md": report, "中文摘要.md": chinese,
               "metrics.json": json.dumps(metrics, ensure_ascii=False, indent=2, allow_nan=False)+"\n",
               "TRAJECTORIES.md": trajectories_text(stages),
               "EXPLANATION_AUDIT.jsonl": "".join(json.dumps(row, ensure_ascii=False, allow_nan=False)+"\n" for row in audits),
               "EXPLANATION_AUDIT.md": audit_text(audits)}
    for path, expected_hash in hashes.items():
        require(hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected_hash, f"Source changed while reporting: {path}")
    require(runner.code_fingerprint() == freeze["code_hash"], "Source code changed while reporting")
    output.mkdir(parents=True, exist_ok=True)
    for name, content in outputs.items():
        temporary = output / (name + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(output / name)
    return {"status": metrics["status"], "formal_present": len(formal["rows"]),
            "development_present": len(stages["development"]["rows"]),
            "audit_attempts": len(audits), "output_dir": str(output), "files": list(outputs)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment_root", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--repo", type=Path, required=True, help="Frozen source checkout, including its data generator")
    parser.add_argument("--require-complete", action="store_true", help="Refuse to write unless all 180 formal + 36 development episodes are terminal")
    parser.add_argument("--skip-reference", action="store_true", help="Skip regenerating deterministic test data / saved-coefficient reference scoring")
    args = parser.parse_args()
    root, output, repo = args.experiment_root.resolve(), args.output_dir.resolve(), args.repo.resolve()
    try:
        require(not output.is_relative_to(repo), "Reports must be outside the source repository")
        require(not output.is_relative_to(root), "Reports must be outside the raw experiment root")
        print(json.dumps(write_reports(root, output, repo, args.require_complete, args.skip_reference), ensure_ascii=False))
        return 0
    except (ValidationError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Report not generated: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
