"""Bounded fixed/adaptive analysis episodes; dry-run unless explicitly executed.

The model receives only discovery summaries and explicitly exposed tool results.
Held-out outcomes and generator truth are used only after a valid submission.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict, dataclass
import hashlib
import io
import json
import math
import os
from pathlib import Path
import time
from typing import Any, Callable


BASE_PROMPT = """You are selecting a predictive model using discovery data only.
Prefer reproducible cross-validation evidence over training fit or unsupported claims.
Use only the provided summaries and actual tool results. Do not invent analyses.
Return exactly one JSON object, without markdown or additional prose.
Available schemas (no extra fields):
{"tool":"fit_model","spec":{"kind":"null"}}
{"tool":"fit_model","spec":{"kind":"linear"}}
{"tool":"fit_model","spec":{"kind":"interaction","pair":["X1","X2"]}}
{"tool":"fit_model","spec":{"kind":"conditional","pair":["X1","X2"],"gate":"X3"}}
{"tool":"diagnose","model_id":"exposed model ID","mode":"pairwise"}
{"tool":"diagnose","model_id":"exposed model ID","mode":"stability","term":["X1","X2"]}
{"tool":"submit","model_id":"exposed model ID","evidence_ids":["fit:chosen model ID"],"explanation":"evidence-grounded explanation"}
Feature names must exist in the supplied data; pair members and gate are distinct.
Use only model and evidence IDs already exposed. Submit must cite the selected
model's own fit evidence ID, with any additional supporting evidence IDs.
The null model is an intercept, linear includes all main effects, interaction adds
one product to those main effects, and conditional permits the pair's interaction
to differ between gate <= 0 and gate > 0. No test outcomes are available.
"""


class EpisodeError(ValueError):
    """An intentional, safe-to-log episode failure code."""


@dataclass(frozen=True)
class Config:
    model: str = "openai/gpt-4.1"
    folds: int = 5
    max_steps: int = 8
    top_k: int = 10
    n_samples: int = 1000
    n_discovery: int = 700
    mode: str = "execute"
    blas_threads: int = 1


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def code_fingerprint() -> str:
    """Hash experiment code and the unchanged transport, never local credentials."""
    here = Path(__file__).resolve().parent
    root = here.parents[1]
    files = (sorted(here.glob("*.py")) + sorted((root / "src").glob("*.py"))
             + sorted((root / "datasets").glob("*.py"))
             + [root / "pyproject.toml", root / "uv.lock"])
    parts = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in files if p.is_file()}
    return digest(parts)


def build_config_hash(config: Config, *, seed: int, condition: str,
                      workflow: str, fingerprint: str, code_hash: str) -> str:
    return digest({"config": asdict(config), "seed": seed, "condition": condition,
                   "workflow": workflow, "data_fingerprint": fingerprint,
                   "code_hash": code_hash, "system_prompt": BASE_PROMPT,
                   "transport": {"temperature": 0.7, "max_tokens": 4096},
                   "protocol_version": 1})


def parse_action(content: str, features: set[str], *, allowed_tools: set[str],
                 exposed_models: set[str], evidence_ids: set[str]) -> dict:
    """Strict JSON/action validation; malformed output is never auto-repaired."""
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise EpisodeError("duplicate_json_key")
            result[key] = value
        return result

    def reject_constant(_):
        raise EpisodeError("nonfinite_json_value")

    try:
        action = json.loads(content, object_pairs_hook=no_duplicates,
                            parse_constant=reject_constant)
    except (json.JSONDecodeError, TypeError):
        raise EpisodeError("invalid_json") from None
    if not isinstance(action, dict):
        raise EpisodeError("action_must_be_object")
    tool = action.get("tool")
    if not isinstance(tool, str) or tool not in allowed_tools:
        raise EpisodeError("unknown_or_disallowed_tool")

    def exact(obj, keys):
        if not isinstance(obj, dict) or set(obj) != set(keys):
            raise EpisodeError("invalid_action_fields")

    def pair(value):
        if (not isinstance(value, list) or len(value) != 2
                or not all(isinstance(v, str) and v in features for v in value)
                or value[0] == value[1]):
            raise EpisodeError("invalid_pair")

    def model_id(value):
        if not isinstance(value, str) or value not in exposed_models:
            raise EpisodeError("unexposed_model_id")

    if tool == "fit_model":
        exact(action, {"tool", "spec"})
        spec = action["spec"]
        if not isinstance(spec, dict):
            raise EpisodeError("invalid_spec")
        kind = spec.get("kind")
        if kind in ("null", "linear"):
            exact(spec, {"kind"})
        elif kind == "interaction":
            exact(spec, {"kind", "pair"})
            pair(spec["pair"])
        elif kind == "conditional":
            exact(spec, {"kind", "pair", "gate"})
            pair(spec["pair"])
            gate = spec["gate"]
            if not isinstance(gate, str) or gate not in features or gate in spec["pair"]:
                raise EpisodeError("invalid_gate")
        else:
            raise EpisodeError("invalid_model_kind")
    elif tool == "diagnose":
        mode = action.get("mode")
        if mode == "pairwise":
            exact(action, {"tool", "model_id", "mode"})
        elif mode == "stability":
            exact(action, {"tool", "model_id", "mode", "term"})
            pair(action["term"])
        else:
            raise EpisodeError("invalid_diagnose_mode")
        model_id(action["model_id"])
    else:
        exact(action, {"tool", "model_id", "evidence_ids", "explanation"})
        model_id(action["model_id"])
        cited = action["evidence_ids"]
        if (not isinstance(cited, list) or not cited
                or not all(isinstance(i, str) and i in evidence_ids for i in cited)
                or len(cited) != len(set(cited))):
            raise EpisodeError("invalid_evidence_ids")
        if "fit:" + action["model_id"] not in cited:
            raise EpisodeError("selected_model_evidence_required")
        if not isinstance(action["explanation"], str) or not action["explanation"].strip():
            raise EpisodeError("empty_explanation")
    return action


def numeric_usage(usage: Any) -> dict:
    """Retain reported usage numbers, without arbitrary transport fields."""
    if not isinstance(usage, dict):
        return {}
    accepted = {"prompt_tokens", "completion_tokens", "total_tokens", "cost",
                "cost_details", "prompt_tokens_details", "completion_tokens_details",
                "is_byok"}

    def numbers(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and math.isfinite(value):
            return value
        if isinstance(value, dict):
            return {k: v for k, raw in value.items()
                    if isinstance(k, str) and (v := numbers(raw)) is not None}
        return None

    return {key: value for key, raw in usage.items()
            if key in accepted and (value := numbers(raw)) is not None}


def usage_totals(events: list[dict]) -> dict:
    usages = [e.get("usage", {}) for e in events if e.get("type") == "model_call"]
    def reported(value):
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value) and value >= 0)

    result = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        known = [u[key] for u in usages if reported(u.get(key))]
        result[key] = sum(known) if len(known) == len(usages) else None
    costs = [u["cost"] for u in usages if reported(u.get("cost"))]
    # A partial sum is not the total bill. Zero is exact only with no API calls.
    result["reported_cost"] = sum(costs) if len(costs) == len(usages) else None
    result["reported_cost_partial"] = sum(costs) if costs or not usages else None
    result["calls_with_reported_cost"] = len(costs)
    result["calls_missing_reported_cost"] = len(usages) - len(costs)
    result["cost_is_complete"] = len(costs) == len(usages)
    result["model_calls"] = len(usages)
    return result


def attempt_costs(attempt: dict) -> dict:
    usage = usage_totals(attempt.get("events", []))
    stats = attempt.get("stats", {})
    return {"fit_count": stats.get("cv_fits", 0) + stats.get("final_fits", 0),
            "analysis_requests": sum(e["type"] == "tool_result" for e in attempt.get("events", [])),
            "model_calls": usage["model_calls"],
            "input_tokens": usage["prompt_tokens"],
            "output_tokens": usage["completion_tokens"],
            "total_tokens": usage["total_tokens"],
            "reported_cost": usage["reported_cost"],
            "reported_cost_partial": usage["reported_cost_partial"],
            "calls_missing_reported_cost": usage["calls_missing_reported_cost"],
            "cost_is_complete": usage["cost_is_complete"],
            "elapsed_seconds": attempt.get("total_seconds")}


def flatten_episode(record: dict) -> dict:
    """One outcome per episode, with costs including every retained attempt."""
    attempts = record.get("previous_attempts", []) + [record]
    costs = [attempt_costs(a) for a in attempts]
    events = [e for a in attempts for e in a.get("events", [])]
    cumulative = attempt_costs({"events": events})
    for key in ("fit_count", "analysis_requests", "elapsed_seconds"):
        values = [cost[key] for cost in costs]
        cumulative[key] = sum(values) if all(value is not None for value in values) else None
    return {"seed": record["seed"], "condition": record["condition"],
            "workflow": record["workflow"], "status": record["status"],
            "requested_model": record.get("requested_model", record["config"]["model"]),
            "actual_model": record.get("actual_model"),
            "attempt_count": len(attempts),
            "failed_attempt_count": sum(a.get("status") == "failed" for a in attempts),
            "incomplete_attempt_count": sum(a.get("status") not in {"failed", "success"} for a in attempts),
            **cumulative, "latest_attempt_costs": costs[-1],
            **(record.get("metrics") or {}), "status": record["status"]}


def atomic_save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temp.replace(path)


def analysis_call(config: Config, function: Callable, *args, **kwargs):
    """Use the same BLAS budget for both workflows (an sklearn dependency)."""
    from threadpoolctl import threadpool_limits

    with threadpool_limits(limits=config.blas_threads):
        return function(*args, **kwargs)


def run_episode(*, case: Any, seed: int, condition: str, workflow: str,
                config: Config, output: Path, code_hash: str,
                session_factory: Callable, summary_factory: Callable,
                scorer: Callable, transport: Callable | None = None,
                retry_failed: bool = False) -> dict:
    """Run or resume an episode, with every model/tool turn persisted."""
    episode_hash = build_config_hash(config, seed=seed, condition=condition,
                                    workflow=workflow, fingerprint=case.fingerprint,
                                    code_hash=code_hash)
    path = output / f"{condition}_{seed}_{workflow}_{episode_hash[:16]}.json"
    attempts = []
    if path.exists():
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            raise EpisodeError("unreadable_existing_artifact") from None
        if not isinstance(previous, dict) or previous.get("config_hash") != episode_hash:
            raise EpisodeError("existing_config_mismatch")
        if previous.get("status") == "success":
            return previous
        if not retry_failed:
            return previous
        attempts = previous.get("previous_attempts", []) + [
            {k: v for k, v in previous.items() if k != "previous_attempts"}]

    started = time.monotonic()
    record = {"config_hash": episode_hash, "code_hash": code_hash,
              "config": asdict(config), "seed": seed, "condition": condition,
              "requested_model": config.model, "actual_model": None,
              "workflow": workflow, "data_fingerprint": case.fingerprint,
              "status": "running", "attempt": len(attempts) + 1,
              "previous_attempts": attempts, "events": [], "submission": None,
              "metrics": None, "artifact_path": str(path), "records": {},
              "stats": {}, "llm_seconds": 0.0}
    session = None

    def persist():
        if session is not None:
            record["records"] = session.records
            record["stats"] = dict(session.stats)
            record["exposed_model_ids"] = sorted(session.exposed_model_ids)
            record["exposed_evidence_ids"] = sorted(session.evidence_ids)
        record["usage"] = usage_totals(record["events"])
        record["cumulative_usage"] = usage_totals(
            [e for a in attempts for e in a.get("events", [])] + record["events"])
        record["total_seconds"] = time.monotonic() - started
        atomic_save(path, record)

    persist()
    try:
        session = analysis_call(config, session_factory, case.discovery, seed=seed,
                                folds=config.folds, top_k=config.top_k)
        summary = analysis_call(config, summary_factory, case.discovery)
        features = set(case.discovery.columns) - {"Y"}
        history = []
        if workflow in {"fixed", "offline_reference"}:
            result = analysis_call(config, session.fixed_evidence)
            history.append({"action": {"tool": "fixed_evidence"}, "result": result})
            record["events"].append({"type": "tool_result", **history[-1]})
            persist()

        if workflow == "offline_reference":
            chosen = min(session.exposed_model_ids,
                         key=lambda mid: (session.records[mid]["cv_mse"], mid))
            submission = {"tool": "submit", "model_id": chosen,
                          "evidence_ids": ["fit:" + chosen],
                          "explanation": "Offline reference: select the exposed candidate with minimum discovery CV MSE; no LLM used."}
        else:
            if transport is None:
                raise EpisodeError("transport_required")
            submission = None
            analysis_steps = 0
            while submission is None:
                final_only = workflow == "fixed" or analysis_steps >= config.max_steps
                allowed = {"submit"} if final_only else {"fit_model", "diagnose", "submit"}
                payload = {"discovery_summary": summary, "history": history,
                           "analysis_actions_remaining": 0 if final_only else config.max_steps - analysis_steps,
                           "allowed_tools": sorted(allowed),
                           "instruction": "Submit an exposed model now." if final_only else "Choose the next analysis action or submit."}
                user_prompt = canonical(payload)
                event = {"type": "model_call", "round": len([e for e in record["events"] if e["type"] == "model_call"]) + 1,
                         "requested_model": config.model, "actual_model": None,
                         "system_prompt": BASE_PROMPT, "user_prompt": user_prompt,
                         "prompt_hash": digest({"system": BASE_PROMPT, "user": user_prompt}),
                         "status": "pending"}
                record["events"].append(event)
                persist()
                call_started = time.monotonic()
                try:
                    # The reused transport prints arbitrary exceptions; never expose those.
                    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                        response = transport(config.model, BASE_PROMPT, user_prompt, event["round"])
                except Exception:
                    event["status"] = "failed"
                    raise EpisodeError("transport_exception") from None
                finally:
                    elapsed = time.monotonic() - call_started
                    event["seconds"] = elapsed
                    record["llm_seconds"] += elapsed
                if not isinstance(response, dict):
                    event["status"] = "failed"
                    raise EpisodeError("invalid_transport_response")
                event["usage"] = numeric_usage(response.get("usage"))
                if response.get("status") != "success":
                    event["status"] = "failed"
                    raise EpisodeError("api_failure")
                content = response.get("content")
                event["content"] = content if isinstance(content, str) else None
                event["status"] = "received"
                persist()
                action = parse_action(content, features, allowed_tools=allowed,
                                      exposed_models=session.exposed_model_ids,
                                      evidence_ids=session.evidence_ids)
                event["action"] = action
                event["status"] = "valid"
                if action["tool"] == "submit":
                    submission = action
                else:
                    analysis_steps += 1
                    if action["tool"] == "fit_model":
                        result = analysis_call(config, session.fit_model, action["spec"])
                    else:
                        result = analysis_call(config, session.diagnose, action["model_id"],
                                               action["mode"], term=action.get("term"))
                    history.append({"action": action, "result": result})
                    record["events"].append({"type": "tool_result", **history[-1]})
                persist()

        record["submission"] = submission
        persist()
        # This is the first point at which held-out data is accessed.
        chosen_id = submission["model_id"]
        predictions = analysis_call(config, session.predict, chosen_id, case.test.drop(columns=["Y"]))
        record["metrics"] = analysis_call(config, scorer, case, session.records[chosen_id], predictions)
        record["status"] = "success"
    except (KeyboardInterrupt, SystemExit):
        record["status"] = "failed"
        record["failure"] = {"code": "interrupted"}
        persist()
        raise
    except EpisodeError as exc:
        record["status"] = "failed"
        record["failure"] = {"code": str(exc)}
    except Exception as exc:
        record["status"] = "failed"
        # No exception text: HTTP failures can contain credentials or request bodies.
        record["failure"] = {"code": "analysis_or_scoring_failure",
                             "exception_type": type(exc).__name__}
    persist()
    return record


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    mode = result.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true", help="Run real model calls; requires OPENROUTER_KEY.")
    mode.add_argument("--offline", action="store_true", help="Run a deterministic fixed-analysis reference, with no LLM.")
    result.add_argument("--seeds", type=int, nargs="+", default=list(range(101, 111)))
    result.add_argument("--conditions", nargs="+", choices=["global", "conditional", "null"],
                        default=["global", "conditional", "null"])
    result.add_argument("--workflows", nargs="+", choices=["fixed", "adaptive"], default=["fixed", "adaptive"])
    result.add_argument("--model", default="openai/gpt-4.1")
    result.add_argument("--folds", type=int, default=5)
    result.add_argument("--max-steps", type=int, default=8)
    result.add_argument("--top-k", type=int, default=10)
    result.add_argument("--n-samples", type=int, default=1000)
    result.add_argument("--n-discovery", type=int, default=700)
    result.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "artifacts")
    result.add_argument("--retry-failed", action="store_true", help="Explicitly retry failed/incomplete episodes, preserving the previous attempt.")
    return result


def main(argv=None) -> int:
    cli = parser()
    args = cli.parse_args(argv)
    if any(seed < 0 for seed in args.seeds) or len(args.seeds) != len(set(args.seeds)):
        cli.error("Seeds must be nonnegative and unique.")
    if (len(args.conditions) != len(set(args.conditions))
            or len(args.workflows) != len(set(args.workflows))):
        cli.error("Conditions and workflows must not contain duplicates.")
    if (args.folds < 2 or args.max_steps < 1 or args.top_k < 1
            or args.n_discovery <= args.folds or args.n_samples <= args.n_discovery):
        cli.error("Require folds >= 2, max-steps/top-k >= 1, and folds < n-discovery < n-samples.")
    mode = "execute" if args.execute else "offline_reference" if args.offline else "dry_run"
    workflows = ["offline_reference"] if args.offline else args.workflows
    config = Config(model=args.model, folds=args.folds, max_steps=args.max_steps,
                    top_k=args.top_k, n_samples=args.n_samples,
                    n_discovery=args.n_discovery, mode=mode)
    plan = {"mode": mode, "config": asdict(config),
            "seeds": args.seeds, "conditions": args.conditions, "workflows": workflows,
            "episode_count": len(args.seeds) * len(args.conditions) * len(workflows),
            "output": str(args.output),
            "maximum_model_calls": 0 if args.offline else len(args.seeds) * len(args.conditions)
                * sum(1 if w == "fixed" else args.max_steps + 1 for w in workflows),
            "note": "Offline reference is deterministic model selection, not a fixed/adaptive AI comparison."
                if args.offline else "Dry-run makes no API calls or statistical fits." if not args.execute
                else "Failed episodes are not retried unless --retry-failed is provided."}
    print(json.dumps(plan, indent=2))
    if mode == "dry_run":
        return 0
    transport = None
    if args.execute:
        # Presence/emptiness is checked before importing data or performing any fit.
        if not os.environ.get("OPENROUTER_KEY"):
            print("OPENROUTER_KEY is required for --execute; no episodes were run.")
            return 2
        from src import run_ai_scientists
        if not run_ai_scientists.OPENROUTER_KEY:
            print("Transport credentials are unavailable; no episodes were run.")
            return 2
        transport = run_ai_scientists.call_openrouter

    from .analysis import AnalysisSession
    from .data import make_case, make_summary
    from .evaluate import aggregate, score_submission

    code_hash = code_fingerprint()
    results = []
    for seed in args.seeds:
        for condition in args.conditions:
            case = make_case(seed, condition, n_samples=args.n_samples,
                             n_discovery=args.n_discovery)
            for workflow in workflows:
                episode = run_episode(case=case, seed=seed, condition=condition,
                                      workflow=workflow, config=config, output=args.output,
                                      code_hash=code_hash, session_factory=AnalysisSession,
                                      summary_factory=make_summary, scorer=score_submission,
                                      transport=transport, retry_failed=args.retry_failed)
                results.append(episode)
                print(f"{condition} seed={seed} {workflow}: {episode['status']}")
                flat = [flatten_episode(r) for r in results]
                report = {"plan": plan, "code_hash": code_hash,
                          "episodes": [r["artifact_path"] for r in results],
                          "runs": flat,
                          "aggregate": aggregate(flat)}
                atomic_save(args.output / ("offline_summary.json" if args.offline else "summary.json"), report)
    return 0 if all(r["status"] == "success" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
