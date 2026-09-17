"""Dataset access, regeneration of the gitignored full CSVs, and verification.

The upstream repository commits only 10-row samples; the 1000-row CSVs read by
the upstream summary function are gitignored.  We regenerate them by calling
the upstream generator functions in exactly the order used by its ``main()``,
with the upstream's fixed seed, and then verify that (a) the first 10 rows are
byte-identical to the committed samples and (b) correlations and OLS R^2 match
the committed baseline JSONs.  Committed files are never written.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .common import sha256_file
from .paths import DATASETS_DIR, REPO_ROOT, UPSTREAM_RESULTS
from .stats import FEATURE_NAMES, ols_with_intercept
from . import upstream


class DatasetVerificationError(RuntimeError):
    pass


def dataset_path(cfg: dict, name: str) -> Path:
    return REPO_ROOT / cfg["datasets"][name]["path"]


def sample_path(cfg: dict, name: str) -> Path:
    return REPO_ROOT / cfg["datasets"][name]["sample_path"]


def regenerate_in_memory() -> dict[str, pd.DataFrame]:
    """Mirror upstream ``main()`` draw order exactly, without writing files."""
    g = upstream.generator_module()
    rng = np.random.default_rng(g.SEED)
    features = g.generate_features(rng, g.N_SAMPLES)
    live_y = g.generate_live_target(features, rng)
    dead_y = g.generate_dead_target(rng, g.N_SAMPLES)
    live = features.copy()
    live["Y"] = live_y
    dead = features.copy()
    dead["Y"] = dead_y
    return {"live_salmon": live, "dead_salmon": dead}


def ensure_full_datasets(cfg: dict) -> dict[str, dict]:
    """Create the gitignored full CSVs that are absent.  Existing files are left as is.

    ``regenerate_in_memory`` always produces both frames, because the two datasets share
    one RNG stream and the dead target can only be drawn after the live one.  Only the
    frames for files that were actually missing may be written: overwriting a file that
    is already on disk would destroy whatever is there before ``verify_datasets`` has had
    a chance to compare it against the committed samples and baselines, which is exactly
    the difference that check exists to surface.
    """
    info: dict[str, dict] = {}
    missing = [n for n in cfg["datasets"] if not dataset_path(cfg, n).exists()]
    frames = regenerate_in_memory() if missing else {}
    for name in cfg["datasets"]:
        p = dataset_path(cfg, name)
        created = name in missing
        if created:
            frames[name].to_csv(p, index=False)       # same call as upstream main()
        info[name] = {"path": str(p.relative_to(REPO_ROOT)), "regenerated_now": created}
    return info


def load_dataset(cfg: dict, name: str) -> pd.DataFrame:
    df = pd.read_csv(dataset_path(cfg, name))
    expected = FEATURE_NAMES + ["Y"]
    if list(df.columns) != expected:
        raise DatasetVerificationError(f"{name}: unexpected columns {list(df.columns)}")
    return df


def verify_datasets(cfg: dict) -> dict:
    """Check full CSVs against committed samples and committed baseline stats."""
    out: dict = {}
    for name in cfg["datasets"]:
        df = load_dataset(cfg, name)
        sp = sample_path(cfg, name)
        committed_sample = sp.read_text()
        # Text-level comparison: header + first 10 data lines of the full CSV must be
        # byte-identical to the committed sample (avoids float re-parsing artefacts).
        with open(dataset_path(cfg, name)) as fh:
            head_lines = [next(fh) for _ in range(11)]
        head_match = "".join(head_lines) == committed_sample

        baseline_path = UPSTREAM_RESULTS / f"baseline_{name}.json"
        baseline = json.loads(baseline_path.read_text())
        corr = df.corr()["Y"].drop("Y")
        corr_max_abs_diff = max(abs(round(float(corr[k]), 4) - v) for k, v in baseline["correlations"].items())
        res = ols_with_intercept(df[FEATURE_NAMES].to_numpy(), df["Y"].to_numpy())
        r2_match = round(res.r2, 4) == baseline["ols"]["r2"]

        out[name] = {
            "n_rows": int(len(df)),
            "full_csv_sha256": sha256_file(dataset_path(cfg, name)),
            "committed_sample_sha256": sha256_file(sp),
            "head10_matches_committed_sample": head_match,
            "baseline_json": str(baseline_path.relative_to(REPO_ROOT)),
            "baseline_n_samples": baseline["n_samples"],
            "corr_with_y_max_abs_diff_vs_baseline_4dp": corr_max_abs_diff,
            "ols_r2_4dp": round(res.r2, 4),
            "ols_r2_matches_baseline": r2_match,
        }
        problems = []
        if not head_match:
            problems.append("first 10 rows differ from committed sample")
        if len(df) != baseline["n_samples"]:
            problems.append("row count differs from baseline")
        if corr_max_abs_diff > 1e-9:
            problems.append("correlations differ from committed baseline")
        if not r2_match:
            problems.append("OLS R^2 differs from committed baseline")
        if problems:
            raise DatasetVerificationError(f"{name}: " + "; ".join(problems))
    out["generator_script_sha256"] = sha256_file(DATASETS_DIR / "generate_live_salmon_data.py")
    out["ground_truth_json_sha256"] = sha256_file(DATASETS_DIR / "ground_truth.json")
    return out
