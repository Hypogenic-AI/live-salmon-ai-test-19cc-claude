"""Experiment runner: dry-run by default, explicit --execute for real calls.

Design points
* One record per scheduled call, stored under runs/<phase>/records/.  The file
  name and the embedded cache key include phase, dataset, condition, model,
  prompt hash, request settings and repetition.
* Bounded retries for technical failures only (network error, timeout, HTTP
  429/5xx, structurally malformed or empty response).  The paper text is never
  inspected when deciding whether to retry.
* Output truncation (finish_reason == "length") is flagged, never retried and
  never silently trimmed.
* An *explicit* provider refusal (a non-empty ``message.refusal``, or a
  content-filter finish reason) is a terminal third outcome: status "refused".
  It is never retried, its raw response, refusal text, finish reason and usage
  are kept, it is counted separately in the phase summary, and it is never
  exported as a paper for claim scoring.  This is distinct from a malformed or
  empty response, which stays a technical failure with bounded retries.
* The provider's returned model string is stored next to the requested one and
  a mismatch is flagged, never silently accepted or substituted.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from .common import sha256_text, utc_now, write_json, read_json
from .schedule import build_schedule
from . import upstream

PostFn = Callable[[str, dict, dict, float], tuple[int, object]]


class TransientFailure(Exception):
    """Technical failure that may be retried."""


class PermanentFailure(Exception):
    """Failure that must not be retried (auth, bad request, ...)."""


class ContentRefusal(Exception):
    """The provider answered, and the answer is an explicit refusal.

    Terminal by construction: the model declining is an observation about this
    call, not a transport fault, so retrying would be replacement sampling on
    content.  Carries the parsed response fields so the record keeps them.
    """

    def __init__(self, reason: str, parsed: dict):
        super().__init__(reason)
        self.reason = reason
        self.parsed = parsed


# Finish reasons that state a content decision rather than a normal stop.  Kept to
# values providers actually document; anything else falls through to the ordinary
# structural checks.
CONTENT_FILTER_FINISH_REASONS = frozenset({
    "content_filter",       # OpenAI / OpenRouter normalised
    "refusal",              # Anthropic native stop reason
    "safety",               # Gemini native
    "blocklist",
    "prohibited_content",
    "image_safety",
    "spii",
})


def is_content_filter(finish_reason: object) -> bool:
    if not isinstance(finish_reason, str):
        return False
    return finish_reason.strip().lower().replace("-", "_") in CONTENT_FILTER_FINISH_REASONS


def default_post_fn(url: str, payload: dict, headers: dict, timeout: float) -> tuple[int, object]:
    import httpx  # imported lazily so offline tooling does not need it
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:          # connection errors, timeouts, protocol errors
        raise TransientFailure(f"{type(exc).__name__}: {exc}") from exc
    try:
        body: object = resp.json()
    except ValueError:
        body = resp.text
    return resp.status_code, body


def classify_status(status: int) -> str:
    if status == 200:
        return "ok"
    if status == 429 or 500 <= status <= 599 or status == 408:
        return "transient"
    return "permanent"


def parse_success_body(body: object) -> dict:
    """Extract the fields we store.

    Three outcomes, checked in this order:

    1. Structural problems (not JSON, no choices) are transient failures.
    2. An explicit refusal -- a non-empty ``message.refusal``, or a content-filter
       finish reason -- raises ``ContentRefusal``.  This is checked *before* the
       content validation below, because a refusal legitimately arrives with
       ``content: null``; treating it as "content missing" would misclassify a
       terminal answer as a malformed response and retry it three times.
    3. Only then is the content validated.  Missing, non-string or whitespace-only
       content is a structural fault and stays a transient failure.

    The *text* of a paper is still never examined; the refusal check reads a
    dedicated protocol field and the finish reason, not the prose.
    """
    if not isinstance(body, dict):
        raise TransientFailure("response body is not a JSON object")
    if "error" in body and not body.get("choices"):
        raise TransientFailure(f"provider error object: {json.dumps(body['error'])[:500]}")
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise TransientFailure("response has no choices")
    first = choices[0] or {}
    if not isinstance(first, dict):
        raise TransientFailure(f"choices[0] is {type(first).__name__}, not an object")
    message = first.get("message") or {}
    if not isinstance(message, dict):
        raise TransientFailure(f"message is {type(message).__name__}, not an object")
    content = message.get("content")
    refusal = message.get("refusal")
    parsed = {
        "content": content if isinstance(content, str) else None,
        "refusal": refusal if isinstance(refusal, str) else None,
        "finish_reason": first.get("finish_reason"),
        "native_finish_reason": first.get("native_finish_reason"),
        "response_model": body.get("model"),
        "provider": body.get("provider"),
        "response_id": body.get("id"),
        "response_created": body.get("created"),
        "usage": body.get("usage"),
    }

    if isinstance(refusal, str) and refusal.strip():
        raise ContentRefusal("message.refusal", parsed)
    for field in ("finish_reason", "native_finish_reason"):
        if is_content_filter(parsed[field]):
            raise ContentRefusal(f"{field}={parsed[field]!r}", parsed)

    if not isinstance(content, str):
        raise TransientFailure("message content missing or not a string")
    if content.strip() == "":
        raise TransientFailure("message content is empty")
    return parsed


def build_payload(plan: dict, cfg: dict) -> dict:
    rs = cfg["request_settings"]
    payload = {
        "model": plan["model_id"],
        "messages": [
            {"role": "system", "content": plan["system_prompt"]},
            {"role": "user", "content": plan["user_prompt"]},
        ],
        "temperature": rs["temperature"],
        "max_tokens": rs["max_tokens"],
    }
    if rs.get("seed") is not None:      # only passed when explicitly configured
        payload["seed"] = rs["seed"]
    return payload


def execute_call(plan: dict, cfg: dict, api_key: str, post_fn: PostFn = default_post_fn,
                 sleep_fn: Callable[[float], None] = time.sleep, now_fn: Callable[[], str] = utc_now,
                 provenance: dict | None = None) -> dict:
    retry = cfg["retry"]
    max_attempts = int(retry["max_attempts"])
    backoffs = list(retry["backoff_seconds"])
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
               "HTTP-Referer": "https://github.com/live-salmon-test"}
    payload = build_payload(plan, cfg)
    record = {
        "record_version": 1,
        "phase": plan["phase"], "dataset": plan["dataset"], "condition": plan["condition"], "rep": plan["rep"],
        "cache_key": plan["cache_key"], "model_key": plan["model_key"],
        "requested_model": plan["model_id"], "response_model": None, "provider": None, "model_mismatch": None,
        "prompt_hash": plan["prompt_hash"],
        "system_prompt_sha256": sha256_text(plan["system_prompt"]),
        "user_prompt_sha256": sha256_text(plan["user_prompt"]),
        "request_settings": dict(cfg["request_settings"]),
        "request_url": cfg["openrouter_url"], "timeout_seconds": cfg["timeout_seconds"],
        "status": "failed", "content": None, "refusal": None, "refusal_reason": None,
        "finish_reason": None, "native_finish_reason": None,
        "truncated": None, "usage": None, "response_id": None, "response_created": None,
        "attempts": [], "n_attempts": 0, "started_at": now_fn(), "finished_at": None,
        "raw_response": None, "provenance": provenance or {},
    }
    for attempt in range(1, max_attempts + 1):
        entry = {"attempt": attempt, "started_at": now_fn(), "finished_at": None, "outcome": None,
                 "http_status": None, "error_type": None, "error_message": None}
        try:
            status, body = post_fn(cfg["openrouter_url"], payload, headers, float(cfg["timeout_seconds"]))
            entry["http_status"] = status
            kind = classify_status(status)
            if kind == "permanent":
                raise PermanentFailure(f"HTTP {status}: {str(body)[:500]}")
            if kind == "transient":
                raise TransientFailure(f"HTTP {status}: {str(body)[:500]}")
            parsed = parse_success_body(body)
            entry["outcome"] = "success"
            entry["finished_at"] = now_fn()
            record["attempts"].append(entry)
            record.update({k: v for k, v in parsed.items()})
            record["status"] = "success"
            record["truncated"] = parsed["finish_reason"] == "length" or parsed.get("native_finish_reason") in ("length", "MAX_TOKENS", "max_tokens")
            record["model_mismatch"] = (parsed["response_model"] is not None and parsed["response_model"] != plan["model_id"])
            record["raw_response"] = body
            break
        except ContentRefusal as exc:
            # Terminal. Not retried: the model declining is an observation about this
            # call, and re-rolling it would be replacement sampling on content.
            entry.update(outcome="refusal", error_type="ContentRefusal", error_message=exc.reason,
                         finished_at=now_fn())
            record["attempts"].append(entry)
            record.update(exc.parsed)
            record["status"] = "refused"
            record["refusal_reason"] = exc.reason
            record["truncated"] = exc.parsed["finish_reason"] == "length" or exc.parsed.get("native_finish_reason") in ("length", "MAX_TOKENS", "max_tokens")
            record["model_mismatch"] = (exc.parsed["response_model"] is not None and exc.parsed["response_model"] != plan["model_id"])
            record["raw_response"] = body
            break
        except TransientFailure as exc:
            entry.update(outcome="transient_error", error_type=type(exc).__name__, error_message=str(exc)[:1000], finished_at=now_fn())
            record["attempts"].append(entry)
            if attempt < max_attempts:
                sleep_fn(float(backoffs[min(attempt - 1, len(backoffs) - 1)]) if backoffs else 0.0)
                continue
        except PermanentFailure as exc:
            entry.update(outcome="permanent_error", error_type=type(exc).__name__, error_message=str(exc)[:1000], finished_at=now_fn())
            record["attempts"].append(entry)
            break
    record["n_attempts"] = len(record["attempts"])
    record["finished_at"] = now_fn()
    return record


# ---------------------------------------------------------------------------
# Phase orchestration
# ---------------------------------------------------------------------------

def phase_dir(runs_dir: Path, phase: str) -> Path:
    return runs_dir / phase


def _refusal_row(rec: dict, plan: dict) -> dict:
    """Refusals stay visible in the phase summary even though no paper is scored."""
    return {"dataset": rec.get("dataset"), "condition": rec.get("condition"), "rep": rec.get("rep"),
            "cache_key": rec.get("cache_key"), "record_file": plan["record_file"],
            "refusal_reason": rec.get("refusal_reason"),
            "refusal": (rec.get("refusal") or "")[:500] or None,
            "finish_reason": rec.get("finish_reason"), "native_finish_reason": rec.get("native_finish_reason"),
            "usage": rec.get("usage"), "response_model": rec.get("response_model")}


def _write_schedule(pdir: Path, rec_dir: Path, sched: dict) -> None:
    """Persist the schedule without ever destroying the one that was executed.

    A preview (dry run, or a run with a different --model) must not overwrite the
    record of what an earlier execution actually scheduled.
    """
    path = pdir / "schedule.json"
    if path.exists():
        existing = read_json(path)
        if existing == sched:
            return
        executed = bool(list(rec_dir.glob("*.json"))) or (pdir / "summary.json").exists()
        if executed:
            raise RuntimeError(
                f"{path} describes a schedule that has already been executed and differs from the one "
                f"just built (existing model_id={existing.get('model_id')}, new model_id={sched.get('model_id')}). "
                "Refusing to overwrite the executed schedule. Move or remove the existing "
                f"{pdir.name}/ artefacts first if this is intentional.")
    write_json(path, sched)


def make_plans(phase: str, cfg: dict, bundles: list[dict], model_key: str) -> tuple[dict, list[dict]]:
    models = upstream.upstream_models()
    if model_key not in models:
        raise ValueError(f"model_key {model_key!r} is not in the upstream MODELS table {sorted(models)}")
    model_id = models[model_key]
    sched = build_schedule(phase, cfg, bundles, model_key, model_id)
    by_key = {(b["dataset"], b["condition"]): b for b in bundles}
    plans = []
    for call in sched["calls"]:
        b = by_key[(call["dataset"], call["condition"])]
        plans.append({**call, "phase": phase, "model_key": model_key, "model_id": model_id,
                      "system_prompt": b["system_prompt"], "user_prompt": b["user_prompt"]})
    return sched, plans


def run_phase(phase: str, cfg: dict, bundles: list[dict], *, execute: bool, runs_dir: Path,
              model_key: str | None = None, api_key: str | None = None, post_fn: PostFn = default_post_fn,
              sleep_fn: Callable[[float], None] = time.sleep, retry_failed: bool = False,
              provenance: dict | None = None, pause_between_calls: float = 2.0,
              log: Callable[[str], None] = print) -> dict:
    model_key = model_key or cfg["model_key"]
    sched, plans = make_plans(phase, cfg, bundles, model_key)
    pdir = phase_dir(runs_dir, phase)
    rec_dir = pdir / "records"
    rec_dir.mkdir(parents=True, exist_ok=True)
    _write_schedule(pdir, rec_dir, sched)

    summary = {"phase": phase, "executed": execute, "model_key": model_key, "model_id": sched["model_id"],
               "planned": len(plans), "already_cached_success": 0, "already_cached_refused": 0,
               "skipped_failed": 0, "called": 0,
               "success": 0, "refused": 0, "failed": 0, "truncated": 0, "model_mismatch": 0,
               "refusals": [], "records": [], "generated_at": utc_now()}
    log_path = pdir / "run_log.jsonl"

    def _log(event: dict) -> None:
        with open(log_path, "a") as f:
            f.write(json.dumps({"ts": utc_now(), **event}) + "\n")

    for plan in plans:
        rp = rec_dir / plan["record_file"]
        state = "new"
        existing = None
        if rp.exists():
            existing = read_json(rp)
            if existing.get("cache_key") != plan["cache_key"] or existing.get("phase") != phase:
                raise RuntimeError(f"record {rp.name} does not match its planned identity")
            state = {"success": "cached_success", "refused": "cached_refused"}.get(
                existing.get("status"), "cached_failed")
        row = {"schedule_index": plan["schedule_index"], "dataset": plan["dataset"], "condition": plan["condition"],
               "rep": plan["rep"], "cache_key": plan["cache_key"], "record_file": plan["record_file"], "state": state}
        if state == "cached_success":
            summary["already_cached_success"] += 1
            row["truncated"] = bool(existing.get("truncated"))
            summary["truncated"] += int(bool(existing.get("truncated")))
            summary["model_mismatch"] += int(bool(existing.get("model_mismatch")))
            summary["success"] += 1
        elif state == "cached_refused":
            # Deliberately before the retry_failed branch: an explicit refusal is a
            # recorded outcome, so --retry-failed must not re-roll it either.
            summary["already_cached_refused"] += 1
            summary["refused"] += 1
            summary["model_mismatch"] += int(bool(existing.get("model_mismatch")))
            row["refusal_reason"] = existing.get("refusal_reason")
            summary["refusals"].append(_refusal_row(existing, plan))
        elif state == "cached_failed" and not retry_failed:
            summary["skipped_failed"] += 1
            summary["failed"] += 1
        elif not execute:
            row["state"] = "planned (dry-run, no call made)"
        else:
            if not api_key:
                raise RuntimeError("OPENROUTER_KEY is required for --execute")
            log(f"[{plan['schedule_index']+1}/{len(plans)}] {phase} {plan['dataset']} {plan['condition']} rep{plan['rep']} -> calling {plan['model_id']}")
            rec = execute_call(plan, cfg, api_key, post_fn=post_fn, sleep_fn=sleep_fn, provenance=provenance)
            if existing is not None:                       # keep earlier failed attempts
                rec["previous_attempts"] = existing.get("attempts", []) + existing.get("previous_attempts", [])
            write_json(rp, rec)
            _log({"event": "call", **{k: rec[k] for k in ("phase", "dataset", "condition", "rep", "cache_key", "status", "refusal_reason", "truncated", "model_mismatch", "n_attempts")}})
            summary["called"] += 1
            row["state"] = rec["status"]
            row["truncated"] = bool(rec["truncated"])
            if rec["status"] == "success":
                summary["success"] += 1
                summary["truncated"] += int(bool(rec["truncated"]))
                summary["model_mismatch"] += int(bool(rec["model_mismatch"]))
            elif rec["status"] == "refused":
                summary["refused"] += 1
                summary["model_mismatch"] += int(bool(rec["model_mismatch"]))
                row["refusal_reason"] = rec["refusal_reason"]
                summary["refusals"].append(_refusal_row(rec, plan))
            else:
                summary["failed"] += 1
            if pause_between_calls:
                sleep_fn(pause_between_calls)
        summary["records"].append(row)
    write_json(pdir / ("summary.json" if execute else "dry_run_plan.json"), summary)
    _log({"event": "phase_end", "executed": execute, **{k: summary[k] for k in ("planned", "called", "success", "refused", "failed", "truncated", "model_mismatch")}})
    return summary


# ---------------------------------------------------------------------------
# Execution preflight (freeze, inputs, key)
# ---------------------------------------------------------------------------

def execution_preflight(phase: str, cfg: dict, bundles: list[dict], api_key: str | None, *, exp_dir: Path | None = None,
                        freezes_dir: Path | None = None, model_key: str | None = None) -> dict:
    """Everything that must hold before a real call is made.  Raises RuntimeError.

    ``model_key`` is the identifier the run will actually use (``--model`` if given,
    otherwise the configured one).  It must equal the frozen and manifested choice:
    the freeze covers config.json, so allowing the command line to substitute a
    different model would let a paid run escape the design it claims to follow.
    """
    from .freeze import verify_freeze
    from .manifest import environment_problems, verify_written_inputs
    from .paths import EXP_DIR, FREEZES_DIR, INPUTS_DIR
    from .conditions import check_input_length
    exp_dir = exp_dir or EXP_DIR
    freezes_dir = freezes_dir or FREEZES_DIR
    model_key = model_key or cfg["model_key"]
    problems = []
    if not api_key:
        problems.append("OPENROUTER_KEY is not set")
    if model_key != cfg["model_key"]:
        problems.append(f"requested model {model_key!r} differs from the frozen config.json model_key "
                        f"{cfg['model_key']!r}; change config.json and create a new freeze instead of "
                        f"passing --model")
    problems += [f"environment: {p}" for p in environment_problems(cfg)]
    ok, reason, frozen = verify_freeze(phase, exp_dir, freezes_dir)
    if not ok:
        problems.append(reason)
    manifest_path = INPUTS_DIR / "manifest.json"
    if not manifest_path.exists():
        problems.append("inputs/manifest.json missing: run generate-inputs")
        manifest = None
    else:
        manifest = read_json(manifest_path)
        problems += verify_written_inputs(manifest)
        by_key = {(i["dataset"], i["condition"]): i["hashes"]["combined_sha256"] for i in manifest["inputs"]}
        for b in bundles:
            if by_key.get((b["dataset"], b["condition"])) != b["hashes"]["combined_sha256"]:
                problems.append(f"{b['dataset']}/{b['condition']}: rebuilt prompt differs from inputs/manifest.json; regenerate inputs and re-freeze")
        if manifest["model"]["key"] != cfg["model_key"]:
            problems.append("manifest model key differs from config; regenerate inputs")
        elif manifest["model"]["key"] != model_key:
            problems.append(f"manifest model key {manifest['model']['key']!r} differs from the model this run "
                            f"would call ({model_key!r})")
        # The short key is not enough. It is resolved through src/run_ai_scientists.py::MODELS,
        # which lives outside the experiment directory and is therefore outside DESIGN_GLOBS:
        # upstream could remap "gpt-4.1" to a different identifier and every key-level check
        # would still pass while the run called a different model. Compare what will actually
        # be sent against the identifier the manifest froze.
        try:
            resolved = upstream.upstream_models().get(model_key)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"could not resolve model key {model_key!r} from the upstream table: {exc}")
        else:
            if resolved is None:
                problems.append(f"model key {model_key!r} is no longer in the upstream MODELS table")
            elif resolved != manifest["model"]["id"]:
                problems.append(
                    f"upstream now resolves {model_key!r} to {resolved!r}, but inputs/manifest.json froze "
                    f"{manifest['model']['id']!r}. The upstream MODELS table is outside the design hash, so this "
                    f"would otherwise send a different model than the one the design records. Regenerate inputs "
                    f"and create a new freeze if the change is intended.")
    for b in bundles:
        try:
            check_input_length(b, cfg)
        except Exception as exc:  # noqa: BLE001
            problems.append(str(exc))
    if problems:
        raise RuntimeError("execution preflight failed:\n  - " + "\n  - ".join(problems))
    return {"freeze": {k: frozen[k] for k in ("freeze_file", "design_hash", "git_head", "created_at", "note")},
            "manifest_config_sha256": manifest["config_sha256"] if manifest else None,
            "model_key": model_key}
