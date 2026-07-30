"""Dry-run-first runner for the interaction-threshold experiment."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import httpx
import numpy as np

from common import (
    ALLCLOSE_ATOL,
    ALLCLOSE_RTOL,
    DEFAULT_EXECUTION_OUTPUT_ROOT,
    DEFAULT_RUNNER_OUTPUT_ROOT,
    DEFAULT_OUTPUT_ROOT,
    SEED,
    coefficient_label,
    json_dump,
    load_manifest,
    relative_to_repo,
    safe_model_slug,
    timestamp_utc,
)
from prompting import build_prompt_bundle

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
REQUEST_TEMPERATURE = 0.7
REQUEST_MAX_TOKENS = 4096


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plan interaction-threshold model runs in dry-run mode by default, "
            "or execute real API calls only when --execute is provided."
        )
    )
    parser.add_argument(
        "--coefficients",
        nargs="+",
        type=float,
        default=None,
        help="One or more interaction coefficients to plan. Defaults to all generated conditions.",
    )
    parser.add_argument(
        "--model-id",
        required=True,
        help="A single model id to plan, for example openai/gpt-4.1.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of runs per selected coefficient.",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--execute",
        action="store_true",
        help="Make real API calls. Dry-run remains the default if omitted.",
    )
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicitly keep dry-run mode. This is the default behavior.",
    )
    parser.add_argument(
        "--generated-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Root directory containing generated interaction-threshold datasets.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_RUNNER_OUTPUT_ROOT,
        help="Root directory for dry-run output records.",
    )
    parser.add_argument(
        "--execution-output-root",
        type=Path,
        default=DEFAULT_EXECUTION_OUTPUT_ROOT,
        help="Root directory for real model outputs when --execute is used.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing dry-run or execution records for the selected runs.",
    )
    return parser.parse_args()


def select_coefficients(requested: list[float] | None, manifest: dict) -> list[float]:
    available = [float(value) for value in manifest["coefficients"]]
    if requested is None:
        return available

    selected = []
    for coefficient in requested:
        match = next(
            (
                available_value
                for available_value in available
                if np.allclose(
                    [coefficient],
                    [available_value],
                    atol=ALLCLOSE_ATOL,
                    rtol=ALLCLOSE_RTOL,
                )
            ),
            None,
        )
        if match is None:
            available_text = ", ".join(f"{value:.1f}" for value in available)
            raise ValueError(
                f"Coefficient {coefficient:.3f} was not found in the generated manifest. "
                f"Available coefficients: {available_text}"
            )
        selected.append(match)
    return selected


def output_record_path(
    output_root: Path,
    coefficient: float,
    model_id: str,
    run_id: int,
    prompt_hash_value: str,
) -> Path:
    condition_name = coefficient_label(coefficient)
    model_slug = safe_model_slug(model_id)
    short_hash = prompt_hash_value[:16]
    return output_root / condition_name / model_slug / f"run_{run_id:02d}__{short_hash}.json"


def build_dry_run_record(
    coefficient: float,
    model_id: str,
    run_id: int,
    dataset_path: Path,
    output_path: Path,
    prompt_bundle: dict,
) -> dict:
    return {
        "experiment_name": "interaction_threshold",
        "status": "dry_run_planned",
        "dry_run": True,
        "api_call_made": False,
        "coefficient": coefficient,
        "condition_name": coefficient_label(coefficient),
        "model_id": model_id,
        "run_id": run_id,
        "seed": SEED,
        "timestamp": timestamp_utc(),
        "prompt_hash": prompt_bundle["prompt_hash"],
        "dataset_label": prompt_bundle["dataset_label"],
        "input_dataset_path": relative_to_repo(dataset_path),
        "output_path": relative_to_repo(output_path),
        "prompt_metadata": {
            "system_prompt_chars": len(prompt_bundle["system_prompt"]),
            "user_prompt_chars": len(prompt_bundle["user_prompt"]),
            "data_summary_chars": len(prompt_bundle["data_summary"]),
            "user_prompt_preview": prompt_bundle["user_prompt"][:280],
        },
        "planned_request": {
            "model": model_id,
            "temperature": REQUEST_TEMPERATURE,
            "max_tokens": REQUEST_MAX_TOKENS,
        },
    }


def build_execution_record(
    coefficient: float,
    model_id: str,
    run_id: int,
    dataset_path: Path,
    output_path: Path,
    prompt_bundle: dict,
    response_content: str,
    usage: dict | None,
    status: str,
    error: str | None = None,
) -> dict:
    record = {
        "experiment_name": "interaction_threshold",
        "status": status,
        "dry_run": False,
        "api_call_made": True,
        "coefficient": coefficient,
        "condition_name": coefficient_label(coefficient),
        "model_id": model_id,
        "run_id": run_id,
        "seed": SEED,
        "timestamp": timestamp_utc(),
        "prompt_hash": prompt_bundle["prompt_hash"],
        "dataset_label": prompt_bundle["dataset_label"],
        "input_dataset_path": relative_to_repo(dataset_path),
        "output_path": relative_to_repo(output_path),
        "prompt_metadata": {
            "system_prompt_chars": len(prompt_bundle["system_prompt"]),
            "user_prompt_chars": len(prompt_bundle["user_prompt"]),
            "data_summary_chars": len(prompt_bundle["data_summary"]),
            "user_prompt_preview": prompt_bundle["user_prompt"][:280],
        },
        "request_metadata": {
            "model": model_id,
            "temperature": REQUEST_TEMPERATURE,
            "max_tokens": REQUEST_MAX_TOKENS,
        },
        "response": {
            "content": response_content,
            "usage": usage or {},
        },
    }
    if error:
        record["error"] = error
    return record


def execute_model_call(model_id: str, prompt_bundle: dict, openrouter_key: str) -> tuple[str, dict]:
    """Execute one OpenRouter request and return content plus usage metadata."""
    headers = {
        "Authorization": f"Bearer {openrouter_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/live-salmon-test",
    }
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": prompt_bundle["system_prompt"]},
            {"role": "user", "content": prompt_bundle["user_prompt"]},
        ],
        "temperature": REQUEST_TEMPERATURE,
        "max_tokens": REQUEST_MAX_TOKENS,
    }
    response = httpx.post(OPENROUTER_URL, json=payload, headers=headers, timeout=120.0)
    response.raise_for_status()
    body = response.json()
    return body["choices"][0]["message"]["content"], body.get("usage", {})


def main() -> None:
    args = parse_args()
    if args.runs < 1:
        raise SystemExit("--runs must be at least 1.")

    execute = bool(args.execute)
    dry_run = not execute
    openrouter_key = ""
    if execute:
        openrouter_key = os.environ.get("OPENROUTER_KEY", "")
        if not openrouter_key:
            raise SystemExit(
                "OPENROUTER_KEY is required when --execute is provided. "
                "Dry-run mode remains available without any API key."
            )

    manifest = load_manifest(args.generated_root)
    coefficients = select_coefficients(args.coefficients, manifest)

    planned_count = 0
    cached_count = 0
    written_count = 0
    api_call_count = 0
    target_root = args.execution_output_root if execute else args.output_root

    for coefficient in coefficients:
        condition_name = coefficient_label(coefficient)
        dataset_path = args.generated_root / condition_name / "live_salmon_data.csv"
        if not dataset_path.exists():
            raise FileNotFoundError(
                f"Dataset for {condition_name} was not found at {dataset_path.as_posix()}. "
                "Run the dataset generator first."
            )

        prompt_bundle = build_prompt_bundle(dataset_path)
        for run_id in range(1, args.runs + 1):
            planned_count += 1
            record_path = output_record_path(
                target_root,
                coefficient,
                args.model_id,
                run_id,
                prompt_bundle["prompt_hash"],
            )

            if record_path.exists() and not args.force:
                cached_count += 1
                with record_path.open("r", encoding="utf-8") as handle:
                    cached_record = json.load(handle)
                print(
                    "[CACHED] "
                    f"coef={coefficient:.1f} model={args.model_id} run={run_id} "
                    f"dataset={cached_record['input_dataset_path']} "
                    f"output={cached_record['output_path']}"
                )
                continue

            if dry_run:
                record = build_dry_run_record(
                    coefficient=coefficient,
                    model_id=args.model_id,
                    run_id=run_id,
                    dataset_path=dataset_path,
                    output_path=record_path,
                    prompt_bundle=prompt_bundle,
                )
                json_dump(record_path, record)
                written_count += 1
                print(
                    "[PLAN] "
                    f"coef={coefficient:.1f} model={args.model_id} run={run_id} "
                    f"dataset={record['input_dataset_path']} "
                    f"output={record['output_path']} "
                    f"prompt_hash={record['prompt_hash'][:16]}"
                )
            else:
                print(
                    "[EXECUTE] "
                    f"coef={coefficient:.1f} model={args.model_id} run={run_id} "
                    f"dataset={relative_to_repo(dataset_path)}"
                )
                try:
                    response_content, usage = execute_model_call(
                        args.model_id,
                        prompt_bundle,
                        openrouter_key,
                    )
                    record = build_execution_record(
                        coefficient=coefficient,
                        model_id=args.model_id,
                        run_id=run_id,
                        dataset_path=dataset_path,
                        output_path=record_path,
                        prompt_bundle=prompt_bundle,
                        response_content=response_content,
                        usage=usage,
                        status="success",
                    )
                except Exception as exc:
                    record = build_execution_record(
                        coefficient=coefficient,
                        model_id=args.model_id,
                        run_id=run_id,
                        dataset_path=dataset_path,
                        output_path=record_path,
                        prompt_bundle=prompt_bundle,
                        response_content="",
                        usage={},
                        status="error",
                        error=str(exc),
                    )
                json_dump(record_path, record)
                written_count += 1
                api_call_count += 1
                print(
                    "[SAVED] "
                    f"coef={coefficient:.1f} model={args.model_id} run={run_id} "
                    f"status={record['status']} output={record['output_path']}"
                )

    print(
        f"{'Execution' if execute else 'Dry-run'} complete: planned={planned_count}, "
        f"written={written_count}, cached={cached_count}, api_calls={api_call_count}"
    )


if __name__ == "__main__":
    main()
