"""Precomputed, shuffled call schedule with a recorded scheduling seed."""
from __future__ import annotations

import random

from .cache import cache_key, record_filename
from .conditions import DATASET_ORDER


def build_schedule(phase: str, cfg: dict, bundles: list[dict], model_key: str, model_id: str) -> dict:
    if phase not in cfg["phases"]:
        raise ValueError(f"unknown phase {phase!r}")
    reps = int(cfg["phases"][phase]["repetitions"])
    by_key = {(b["dataset"], b["condition"]): b for b in bundles}
    canonical = []
    for dataset in DATASET_ORDER:
        for condition in cfg["conditions"]:
            for rep in range(1, reps + 1):
                b = by_key[(dataset, condition)]
                key = cache_key(phase, dataset, condition, model_id, b["hashes"]["combined_sha256"],
                                cfg["request_settings"], rep)
                canonical.append({
                    "dataset": dataset, "condition": condition, "rep": rep,
                    "prompt_hash": b["hashes"]["combined_sha256"], "cache_key": key,
                    "record_file": record_filename(phase, dataset, condition, model_key, rep, key),
                })
    seed_string = f"{cfg['scheduling_seed']}:{phase}"
    order = list(range(len(canonical)))
    random.Random(seed_string).shuffle(order)
    shuffled = [dict(canonical[i], schedule_index=k) for k, i in enumerate(order)]
    return {
        "phase": phase,
        "model_key": model_key,
        "model_id": model_id,
        "repetitions_per_combination": reps,
        "planned_calls": len(shuffled),
        "scheduling_seed": cfg["scheduling_seed"],
        "seed_string": seed_string,
        "shuffle_method": "python random.Random(seed_string).shuffle over canonical order",
        "request_settings": cfg["request_settings"],
        "calls": shuffled,
    }
