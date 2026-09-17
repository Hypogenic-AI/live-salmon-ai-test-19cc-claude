"""Cache identity for one model call.

The key covers phase, dataset, condition, model, prompt hash, request settings
and repetition, so smoke records can never be mistaken for formal ones and a
changed prompt or setting always produces a fresh call.
"""
from __future__ import annotations

import hashlib

from .common import canonical_json


def cache_key(phase: str, dataset: str, condition: str, model_id: str, prompt_hash: str,
              request_settings: dict, rep: int) -> str:
    identity = {
        "phase": phase,
        "dataset": dataset,
        "condition": condition,
        "model_id": model_id,
        "prompt_hash": prompt_hash,
        "request_settings": request_settings,
        "rep": int(rep),
    }
    return hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()[:16]


def record_filename(phase: str, dataset: str, condition: str, model_key: str, rep: int, key: str) -> str:
    return f"{phase}__{dataset}__{condition}__{model_key}__rep{int(rep):02d}__{key}.json"
