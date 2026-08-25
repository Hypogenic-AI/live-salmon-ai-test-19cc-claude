"""
Generate synthetic datasets for the "Hidden Breakpoint" task.

Part of the Live Salmon Test suite. This task tests whether AI scientists
can detect structural breaks in time series data.

The "Live" dataset has a known structural break at t=100:
  - Period 1 (t=0..99):   Y = 2.0*X1 + 0.5*X2 + noise
  - Period 2 (t=100..199): Y = -1.5*X1 + 0.8*X3 + noise

A naive analysis pooling both periods will find X1's effect near zero
(the +2.0 and -1.5 partially cancel), completely missing the regime change.

The "Dead" dataset is pure noise throughout (control condition).
"""

import json
import os

import numpy as np
import pandas as pd

SEED = 123
N_SAMPLES = 200
BREAKPOINT = 100
N_FEATURES = 10
NOISE_STD = 1.0
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

REGIME_1_COEFFICIENTS = {"X1": 2.0, "X2": 0.5}
REGIME_2_COEFFICIENTS = {"X1": -1.5, "X3": 0.8}


def generate_features(rng: np.random.Generator, n: int) -> pd.DataFrame:
    """Generate stationary features (same DGP throughout)."""
    data = {f"X{i}": rng.normal(0, 1, n) for i in range(1, N_FEATURES + 1)}
    return pd.DataFrame(data)


def generate_live_target(df: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    """
    Generate Y with a structural break at t=BREAKPOINT.

    Period 1: Y = 2.0*X1 + 0.5*X2 + noise
    Period 2: Y = -1.5*X1 + 0.8*X3 + noise
    """
    y = np.empty(len(df))
    noise = rng.normal(0, NOISE_STD, len(df))

    for t in range(len(df)):
        if t < BREAKPOINT:
            y[t] = (
                REGIME_1_COEFFICIENTS["X1"] * df.iloc[t]["X1"]
                + REGIME_1_COEFFICIENTS["X2"] * df.iloc[t]["X2"]
                + noise[t]
            )
        else:
            y[t] = (
                REGIME_2_COEFFICIENTS["X1"] * df.iloc[t]["X1"]
                + REGIME_2_COEFFICIENTS["X3"] * df.iloc[t]["X3"]
                + noise[t]
            )
    return y


def generate_dead_target(rng: np.random.Generator, n: int) -> np.ndarray:
    """Generate pure noise target (dead salmon / null condition)."""
    return rng.normal(0, 1, n)


def build_ground_truth() -> dict:
    """Return a dictionary describing the true data generating process."""
    return {
        "description": (
            "Hidden Breakpoint task. Time series with a structural break at t=100. "
            "Period 1 (t<100): Y = 2.0*X1 + 0.5*X2 + N(0,1). "
            "Period 2 (t>=100): Y = -1.5*X1 + 0.8*X3 + N(0,1)."
        ),
        "true_formula": {
            "period_1": "Y = 2.0*X1 + 0.5*X2 + epsilon  (t < 100)",
            "period_2": "Y = -1.5*X1 + 0.8*X3 + epsilon  (t >= 100)",
        },
        "breakpoint": BREAKPOINT,
        "noise_distribution": "N(0, 1)",
        "regime_1_coefficients": REGIME_1_COEFFICIENTS,
        "regime_2_coefficients": REGIME_2_COEFFICIENTS,
        "truly_predictive_features": {
            "period_1": ["X1", "X2"],
            "period_2": ["X1", "X3"],
        },
        "noise_features": [f"X{i}" for i in range(4, N_FEATURES + 1)],
        "key_challenge": (
            "Pooling both periods, X1's marginal effect is near zero "
            "(+2.0 and -1.5 partially cancel). AI scientists must detect "
            "the structural break to recover the true model."
        ),
        "n_samples": N_SAMPLES,
        "n_features": N_FEATURES,
        "seed": SEED,
        "dead_salmon_note": (
            "The dead dataset uses the same features but Y is pure N(0,1) "
            "noise throughout. Any 'significant' finding is a false positive."
        ),
    }


def main() -> None:
    rng = np.random.default_rng(SEED)

    features = generate_features(rng, N_SAMPLES)
    features.insert(0, "time", range(N_SAMPLES))

    live_y = generate_live_target(features.drop(columns="time"), rng)
    live_df = features.copy()
    live_df["Y"] = live_y

    dead_y = generate_dead_target(rng, N_SAMPLES)
    dead_df = features.copy()
    dead_df["Y"] = dead_y

    live_path = os.path.join(OUTPUT_DIR, "breakpoint_live_data.csv")
    dead_path = os.path.join(OUTPUT_DIR, "breakpoint_dead_data.csv")
    live_df.to_csv(live_path, index=False)
    dead_df.to_csv(dead_path, index=False)
    print(f"Saved live breakpoint dataset: {live_path}  ({live_df.shape})")
    print(f"Saved dead breakpoint dataset: {dead_path}  ({dead_df.shape})")

    live_sample_path = os.path.join(OUTPUT_DIR, "breakpoint_live_sample.csv")
    dead_sample_path = os.path.join(OUTPUT_DIR, "breakpoint_dead_sample.csv")
    live_df.head(10).to_csv(live_sample_path, index=False)
    dead_df.head(10).to_csv(dead_sample_path, index=False)
    print(f"Saved live sample:  {live_sample_path}")
    print(f"Saved dead sample:  {dead_sample_path}")

    gt = build_ground_truth()
    gt_path = os.path.join(OUTPUT_DIR, "breakpoint_ground_truth.json")
    with open(gt_path, "w") as f:
        json.dump(gt, f, indent=2)
    print(f"Saved ground truth: {gt_path}")

    print("\n--- Sanity check (live breakpoint) ---")
    print(f"  Y mean:  {live_y.mean():.3f}")
    print(f"  Y std:   {live_y.std():.3f}")

    y_series = pd.Series(live_y)
    corrs = features.drop(columns="time").corrwith(y_series)
    print("  Overall correlations with Y (pooling both periods):")
    for feat in corrs.abs().sort_values(ascending=False).head(5).index:
        print(f"    {feat}: {corrs[feat]:+.3f}")

    y1 = live_y[:BREAKPOINT]
    y2 = live_y[BREAKPOINT:]
    f1 = features.drop(columns="time").iloc[:BREAKPOINT].reset_index(drop=True)
    f2 = features.drop(columns="time").iloc[BREAKPOINT:].reset_index(drop=True)
    print(f"\n  Period 1 (t<100) correlations:")
    for feat in ["X1", "X2", "X3"]:
        print(f"    {feat}: {f1[feat].corr(pd.Series(y1)):+.3f}")
    print(f"  Period 2 (t>=100) correlations:")
    for feat in ["X1", "X2", "X3"]:
        print(f"    {feat}: {f2[feat].corr(pd.Series(y2)):+.3f}")

    print("\n--- Sanity check (dead breakpoint) ---")
    dead_corrs = features.drop(columns="time").corrwith(pd.Series(dead_y))
    print(f"  Max |corr| with Y: {dead_corrs.abs().max():.3f}")


if __name__ == "__main__":
    main()
