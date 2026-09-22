"""Paired, blinded variants of the repository's original synthetic datasets.

Only ``discovery`` and ``make_summary(discovery)`` belong in a model prompt.
The held-out data, mapping, and truth are evaluator-private metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
from numbers import Integral
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd


def _load_base_module(name: str, relative_path: str):
    # Use exact local files: an installed HuggingFace ``datasets`` package can
    # otherwise shadow this repository's non-package datasets directory.
    path = Path(__file__).resolve().parents[2] / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load repository module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_base_data = _load_base_module(
    "_adaptive_base_data", "datasets/generate_live_salmon_data.py"
)
_base_summary = _load_base_module(
    "_adaptive_base_summary", "src/prepare_data_summary.py"
)

CONDITIONS = ("global", "conditional", "null")
FEATURE_COLUMNS = tuple(f"X{i}" for i in range(1, 21))


@dataclass(frozen=True)
class DatasetCase:
    discovery: pd.DataFrame
    test: pd.DataFrame
    truth: dict
    fingerprint: str


def _integer(value: int, name: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(value)


def make_case(
    seed: int, condition: str, n_samples: int = 1000, n_discovery: int = 700
) -> DatasetCase:
    """Create a case paired across conditions by features, noise, and row split.

    Randomly relabel the existing 20 variables without changing their values or
    proxy relationships. The conditional case replaces only the original 0.8
    interaction with sqrt(2) * 0.8 * X4 * X5 * I(X6 > 0).
    """
    seed = _integer(seed, "seed", 0)
    n_samples = _integer(n_samples, "n_samples", 2)
    n_discovery = _integer(n_discovery, "n_discovery", 1)
    if n_discovery >= n_samples:
        raise ValueError("n_discovery must be smaller than n_samples")
    if condition not in CONDITIONS:
        raise ValueError(f"condition must be one of {CONDITIONS}")

    feature_seed, target_seed, mapping_seed, split_seed = np.random.SeedSequence(
        seed
    ).spawn(4)
    features = _base_data.generate_features(np.random.default_rng(feature_seed), n_samples)
    # Independent generators from the SAME child seed draw exactly the same
    # Gaussian noise. Calling the two base functions on one advancing RNG would
    # not preserve this pairing.
    live_target = _base_data.generate_live_target(
        features, np.random.default_rng(target_seed)
    )
    null_target = _base_data.generate_dead_target(
        np.random.default_rng(target_seed), n_samples
    )
    interaction = _base_data.INTERACTION_COEFF * features["X4"] * features["X5"]
    if condition == "conditional":
        target = (
            live_target - interaction
            + np.sqrt(2.0) * interaction * (features["X6"] > 0)
        )
    elif condition == "global":
        target = live_target
    else:
        target = null_target

    permutation = np.random.default_rng(mapping_seed).permutation(20)
    mapping = {
        original: f"X{int(permutation[i]) + 1}"
        for i, original in enumerate(FEATURE_COLUMNS)
    }
    data = features.rename(columns=mapping).loc[:, list(FEATURE_COLUMNS)].copy()
    data["Y"] = np.asarray(target, dtype=float)
    row_order = np.random.default_rng(split_seed).permutation(n_samples)
    discovery_rows, test_rows = row_order[:n_discovery], row_order[n_discovery:]
    discovery = data.iloc[discovery_rows].reset_index(drop=True)
    test = data.iloc[test_rows].reset_index(drop=True)

    true_spec: dict = {"kind": "null" if condition == "null" else "interaction"}
    if condition != "null":
        true_spec["pair"] = sorted([mapping["X4"], mapping["X5"]])
    if condition == "conditional":
        true_spec.update(kind="conditional", gate=mapping["X6"])

    roles = {}
    for original in FEATURE_COLUMNS:
        if condition == "null":
            role = "null_feature"
        elif original in _base_data.TRUE_COEFFICIENTS:
            role = "linear_predictor"
        elif original in ("X4", "X5"):
            role = "interaction_predictor"
        elif condition == "conditional" and original == "X6":
            role = "gate"
        elif int(original[1:]) >= 16:
            role = "correlated_noncausal_proxy"
        else:
            role = "noise_distractor"
        roles[mapping[original]] = role

    truth = {
        "seed": seed,
        "condition": condition,
        "spec": true_spec,
        "mapping": mapping,
        "feature_roles": roles,
        "linear_coefficients": {} if condition == "null" else {
            mapping[name]: float(value)
            for name, value in _base_data.TRUE_COEFFICIENTS.items()
        },
        "interaction_coefficient": (
            0.0 if condition == "null" else float(_base_data.INTERACTION_COEFF)
        ),
        "group_slopes": {
            "nonpositive": 0.0,
            "positive": float(np.sqrt(2.0) * _base_data.INTERACTION_COEFF),
        } if condition == "conditional" else None,
        "gate_threshold": 0.0 if condition == "conditional" else None,
        "gate_direction": "positive" if condition == "conditional" else None,
        "discovery_rows": discovery_rows.tolist(),
        "test_rows": test_rows.tolist(),
        "n_samples": n_samples,
        "n_discovery": n_discovery,
        "noise_std": float(_base_data.NOISE_STD),
    }
    digest = hashlib.sha256()
    digest.update(json.dumps({
        "version": 1, "columns": list(discovery.columns),
        "n_discovery": n_discovery, "n_samples": n_samples,
    }, sort_keys=True).encode())
    digest.update(discovery.to_numpy(dtype="<f8").tobytes())
    digest.update(test.to_numpy(dtype="<f8").tobytes())
    return DatasetCase(discovery, test, truth, digest.hexdigest())


def make_summary(discovery: pd.DataFrame) -> str:
    """Reuse the base summary with only the provided discovery rows.

    A neutral label contains no condition, seed, true variable role, or test
    statistic. The base formatter expects the preserved X1..X20,Y column names.
    """
    expected = list(FEATURE_COLUMNS) + ["Y"]
    if list(discovery.columns) != expected:
        raise ValueError("discovery must have columns X1..X20,Y in that order")
    if discovery.empty or not np.isfinite(discovery.to_numpy(dtype=float)).all():
        raise ValueError("discovery must be nonempty and finite")
    with tempfile.TemporaryDirectory(prefix="adaptive-summary-") as directory:
        path = Path(directory) / "discovery.csv"
        discovery.to_csv(path, index=False)
        return _base_summary.prepare_summary(str(path), "Research Dataset")
