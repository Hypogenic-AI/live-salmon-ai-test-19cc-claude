"""Shared utilities for the interaction-threshold dataset benchmark."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

SEED = 42
N_SAMPLES = 1000
N_FEATURES = 20
NOISE_STD = 1.0
DEFAULT_COEFFICIENTS = (0.0, 0.4, 0.8, 1.6)
DEFAULT_OUTPUT_ROOT = Path("experiments/interaction_threshold/generated")
DEFAULT_RUNNER_OUTPUT_ROOT = Path("experiments/interaction_threshold/planned_calls")
DEFAULT_EXECUTION_OUTPUT_ROOT = Path("experiments/interaction_threshold/outputs")
FLOAT_FORMAT = "%.12g"
ALLCLOSE_ATOL = 1e-9
ALLCLOSE_RTOL = 1e-9

LINEAR_COEFFICIENTS = {
    "X1": 2.0,
    "X2": 0.5,
    "X3": -1.5,
}

PROXY_SPECS = {
    "X16": ("X1", 0.7, 0.3),
    "X17": ("X2", 0.6, 0.4),
    "X18": ("X3", 0.5, 0.5),
    "X19": ("X4", 0.8, 0.2),
    "X20": ("X5", 0.65, 0.35),
}

FEATURE_ROLE_GROUPS = {
    "direct_linear_signal_variables": ["X1", "X2", "X3"],
    "interaction_participants": ["X4", "X5"],
    "noise_variables": [f"X{i}" for i in range(6, 16)],
    "correlated_proxy_variables": ["X16", "X17", "X18", "X19", "X20"],
}


def coefficient_label(interaction_coefficient: float) -> str:
    """Convert a coefficient into a stable directory label."""
    coefficient_text = f"{interaction_coefficient:.1f}".replace("-", "m").replace(".", "p")
    return f"coef_{coefficient_text}"


def repo_root() -> Path:
    """Return the repository root from this experiment package."""
    return Path(__file__).resolve().parents[2]


def relative_to_repo(path: Path) -> str:
    """Return a repository-relative path for metadata and logs."""
    return path.resolve().relative_to(repo_root()).as_posix()


def safe_model_slug(model_id: str) -> str:
    """Convert a model id into a filesystem-safe label."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model_id).strip("_") or "model"


def timestamp_utc() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def prompt_hash(system_prompt: str, user_prompt: str) -> str:
    """Return a stable hash of the full model input prompt."""
    payload = f"{system_prompt}\n\n{user_prompt}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def expected_feature_columns() -> list[str]:
    return [f"X{i}" for i in range(1, N_FEATURES + 1)]


def expected_dataset_columns() -> list[str]:
    return expected_feature_columns() + ["Y"]


def generate_base_features_and_noise() -> tuple[pd.DataFrame, pd.Series]:
    """Generate the shared X matrix and epsilon vector.

    The random draw order matches the repository's default generator so that the
    0.8 condition can reproduce the default live-salmon setting.
    """
    rng = np.random.default_rng(SEED)

    x1 = rng.normal(0, 1, N_SAMPLES)
    x2 = rng.normal(0, 1, N_SAMPLES)
    x3 = rng.normal(0, 1, N_SAMPLES)
    x4 = rng.normal(0, 1, N_SAMPLES)
    x5 = rng.normal(0, 1, N_SAMPLES)

    noise_features = {f"X{i}": rng.normal(0, 1, N_SAMPLES) for i in range(6, 16)}

    x16 = 0.7 * x1 + 0.3 * rng.normal(0, 1, N_SAMPLES)
    x17 = 0.6 * x2 + 0.4 * rng.normal(0, 1, N_SAMPLES)
    x18 = 0.5 * x3 + 0.5 * rng.normal(0, 1, N_SAMPLES)
    x19 = 0.8 * x4 + 0.2 * rng.normal(0, 1, N_SAMPLES)
    x20 = 0.65 * x5 + 0.35 * rng.normal(0, 1, N_SAMPLES)

    features = pd.DataFrame(
        {
            "X1": x1,
            "X2": x2,
            "X3": x3,
            "X4": x4,
            "X5": x5,
            **noise_features,
            "X16": x16,
            "X17": x17,
            "X18": x18,
            "X19": x19,
            "X20": x20,
        }
    )

    epsilon = pd.Series(rng.normal(0, NOISE_STD, N_SAMPLES), name="epsilon")
    return features, epsilon


def build_live_dataset(
    features: pd.DataFrame,
    epsilon: pd.Series,
    interaction_coefficient: float,
) -> pd.DataFrame:
    """Construct a live-salmon-style dataset for one interaction coefficient."""
    interaction = features["X4"] * features["X5"]
    y = (
        LINEAR_COEFFICIENTS["X1"] * features["X1"]
        + LINEAR_COEFFICIENTS["X2"] * features["X2"]
        + LINEAR_COEFFICIENTS["X3"] * features["X3"]
        + interaction_coefficient * interaction
        + epsilon
    )

    dataset = features.copy()
    dataset["Y"] = y
    return dataset


def build_ground_truth(interaction_coefficient: float) -> dict:
    """Build coefficient-specific metadata for later evaluation."""
    return {
        "experiment_name": "interaction_threshold",
        "dataset_kind": "live_salmon_style",
        "interaction_coefficient": interaction_coefficient,
        "true_formula": (
            "Y = 2*X1 + 0.5*X2 - 1.5*X3 + "
            f"{interaction_coefficient:.1f}*(X4*X5) + epsilon"
        ),
        "linear_coefficients": LINEAR_COEFFICIENTS,
        "interaction_term": {
            "participants": ["X4", "X5"],
            "coefficient": interaction_coefficient,
        },
        "noise_distribution": "N(0, 1)",
        "noise_std": NOISE_STD,
        "n_samples": N_SAMPLES,
        "n_features": N_FEATURES,
        "seed": SEED,
        "feature_roles": {
            **FEATURE_ROLE_GROUPS,
            "proxy_sources": {proxy: source for proxy, (source, _, _) in PROXY_SPECS.items()},
        },
        "shared_artifacts": {
            "base_features_path": "../shared/base_features.csv",
            "base_noise_path": "../shared/base_noise.csv",
        },
        "notes": (
            "All interaction-threshold conditions share the same X matrix and "
            "epsilon vector. Only the X4*X5 coefficient changes."
        ),
    }


def json_dump(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, float_format=FLOAT_FORMAT)


def write_series_csv(path: Path, series: pd.Series) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    series.to_frame().to_csv(path, index=False, float_format=FLOAT_FORMAT)


def managed_output_paths(output_root: Path, coefficients: Iterable[float]) -> list[Path]:
    """List all generator-managed files that should not be overwritten by default."""
    paths = [
        output_root / "manifest.json",
        output_root / "shared" / "base_features.csv",
        output_root / "shared" / "base_noise.csv",
    ]
    for coefficient in coefficients:
        condition_dir = output_root / coefficient_label(coefficient)
        paths.append(condition_dir / "live_salmon_data.csv")
        paths.append(condition_dir / "ground_truth.json")
    return paths


def load_manifest(output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict:
    """Load the generated dataset manifest."""
    manifest_path = output_root / "manifest.json"
    with manifest_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
