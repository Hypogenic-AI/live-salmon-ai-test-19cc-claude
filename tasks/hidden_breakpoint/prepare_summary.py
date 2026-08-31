"""
Prepare time-series-aware data summaries for AI scientists.

Provides summary statistics, autocorrelations, rolling statistics,
and split-period analyses to help (or hinder) breakpoint detection.
"""

import numpy as np
import pandas as pd


def prepare_summary(csv_path: str, dataset_label: str) -> str:
    """Create a text summary of the time series dataset."""
    df = pd.read_csv(csv_path)
    n = len(df)
    feature_cols = [c for c in df.columns if c not in ("time", "Y")]
    p = len(feature_cols)

    desc = df.describe().round(4).to_string()

    corr_with_y = df[feature_cols + ["Y"]].corr()["Y"].drop("Y").sort_values(ascending=False)
    corr_str = corr_with_y.round(4).to_string()

    full_corr = df[feature_cols + ["Y"]].corr().round(3).to_string()

    sample = df.head(15).round(4).to_csv(index=False)
    sample_tail = df.tail(15).round(4).to_csv(index=False)

    y = df["Y"].values
    acf_lags = []
    y_centered = y - y.mean()
    var = np.var(y)
    for lag in range(1, 11):
        if var > 0:
            r = np.mean(y_centered[:-lag] * y_centered[lag:]) / var
        else:
            r = 0.0
        acf_lags.append((lag, round(r, 4)))

    mid = n // 2
    y_first_half = pd.Series(y[:mid])
    y_second_half = pd.Series(y[mid:])
    first_stats = f"  mean={y_first_half.mean():.3f}, std={y_first_half.std():.3f}"
    second_stats = f"  mean={y_second_half.mean():.3f}, std={y_second_half.std():.3f}"

    corr_first = df[feature_cols].iloc[:mid].corrwith(y_first_half).sort_values(ascending=False)
    corr_second = df[feature_cols].iloc[mid:].corrwith(y_second_half).sort_values(ascending=False)

    corr_first_str = corr_first.round(4).head(5).to_string()
    corr_second_str = corr_second.round(4).head(5).to_string()

    summary = f"""# Dataset: {dataset_label}

## Overview
- Number of time points: {n}
- Number of features: {p} (X1 through X{p})
- Target variable: Y (continuous)
- This is a TIME SERIES dataset (observations ordered by time).
- All features and target are continuous numerical variables.

## Task
You are given a time series dataset with {p} features (X1-X{p}) and a continuous target variable Y, observed over {n} time points.
Your goal is to discover the relationship between the features and Y.
Pay attention to whether the relationship might change over time.

## Summary Statistics
{desc}

## Overall Correlations of each feature with Y (pooled across all time)
{corr_str}

## Y Autocorrelation (first 10 lags)
"""
    for lag, r in acf_lags:
        summary += f"  lag {lag}: r = {r}\n"

    summary += f"""
## Y Statistics by Half
First half (t=0..{mid - 1}):{first_stats}
Second half (t={mid}..{n - 1}):{second_stats}

## Top Feature Correlations with Y — First Half (t=0..{mid - 1})
{corr_first_str}

## Top Feature Correlations with Y — Second Half (t={mid}..{n - 1})
{corr_second_str}

## Full Correlation Matrix (all features + Y)
{full_corr}

## Sample Data (first 15 time points)
{sample}

## Sample Data (last 15 time points)
{sample_tail}

## Raw Data Access
The full dataset has {n} rows. The above summaries represent the complete dataset.
"""
    return summary


if __name__ == "__main__":
    live = prepare_summary("breakpoint_live_data.csv", "Research Dataset C")
    dead = prepare_summary("breakpoint_dead_data.csv", "Research Dataset D")
    print("=== LIVE BREAKPOINT SUMMARY ===")
    print(live[:500])
    print("...")
    print("\n=== DEAD BREAKPOINT SUMMARY ===")
    print(dead[:500])
    print("...")
