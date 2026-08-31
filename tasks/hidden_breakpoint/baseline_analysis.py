"""
Baseline analysis for the Hidden Breakpoint task.

Runs standard statistical methods to establish what traditional
analyses find — both pooled (ignoring time) and split-sample
(accounting for the structural break).
"""

import json
import os
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LassoCV, LinearRegression
from sklearn.model_selection import cross_val_score
import scipy.stats as stats

warnings.filterwarnings("ignore")


def chow_test(y, X1, X2):
    """
    Chow test for structural break between two subsamples.
    X1, X2 are design matrices (with intercept) for period 1 and 2.
    Returns F-statistic and p-value.
    """
    n1, n2 = len(X1), len(X2)
    k = X1.shape[1]

    X_pool = np.vstack([X1, X2])
    y_pool = np.concatenate([y[:n1], y[n1:]])

    beta_pool = np.linalg.lstsq(X_pool, y_pool, rcond=None)[0]
    rss_pool = np.sum((y_pool - X_pool @ beta_pool) ** 2)

    beta1 = np.linalg.lstsq(X1, y[:n1], rcond=None)[0]
    rss1 = np.sum((y[:n1] - X1 @ beta1) ** 2)

    beta2 = np.linalg.lstsq(X2, y[n1:], rcond=None)[0]
    rss2 = np.sum((y[n1:] - X2 @ beta2) ** 2)

    f_stat = ((rss_pool - (rss1 + rss2)) / k) / ((rss1 + rss2) / (n1 + n2 - 2 * k))
    p_value = 1 - stats.f.cdf(f_stat, k, n1 + n2 - 2 * k)
    return round(f_stat, 4), round(p_value, 6)


def analyze_dataset(csv_path: str, label: str) -> dict:
    """Run baseline analyses on a breakpoint dataset."""
    df = pd.read_csv(csv_path)
    feature_cols = [c for c in df.columns if c not in ("time", "Y")]
    X = df[feature_cols]
    y = df["Y"].values
    n = len(df)
    mid = n // 2

    results = {"label": label, "n_samples": n, "n_features": len(feature_cols)}

    # 1. Pooled OLS (ignoring time structure)
    ols = LinearRegression().fit(X, y)
    ols_r2 = ols.score(X, y)
    ols_cv = cross_val_score(ols, X, y, cv=5, scoring="r2").mean()
    pooled_coefs = dict(zip(feature_cols, np.round(ols.coef_, 4)))
    results["pooled_ols"] = {
        "r2": round(ols_r2, 4),
        "cv_r2": round(ols_cv, 4),
        "coefficients": pooled_coefs,
    }

    # 2. Pooled correlations
    pooled_corrs = {}
    pooled_pvals = {}
    for col in feature_cols:
        r, p = stats.pearsonr(X[col], y)
        pooled_corrs[col] = round(r, 4)
        pooled_pvals[col] = round(p, 6)
    results["pooled_correlations"] = pooled_corrs
    results["pooled_corr_pvalues"] = pooled_pvals

    # 3. Split-sample OLS (first half vs second half)
    X1_df, X2_df = X.iloc[:mid], X.iloc[mid:]
    y1, y2 = y[:mid], y[mid:]

    ols1 = LinearRegression().fit(X1_df, y1)
    ols2 = LinearRegression().fit(X2_df, y2)

    results["split_ols"] = {
        "period_1": {
            "r2": round(ols1.score(X1_df, y1), 4),
            "coefficients": dict(zip(feature_cols, np.round(ols1.coef_, 4))),
        },
        "period_2": {
            "r2": round(ols2.score(X2_df, y2), 4),
            "coefficients": dict(zip(feature_cols, np.round(ols2.coef_, 4))),
        },
    }

    # 4. Split-sample correlations
    split_corrs = {"period_1": {}, "period_2": {}}
    for col in feature_cols:
        r1, _ = stats.pearsonr(X1_df[col], y1)
        r2, _ = stats.pearsonr(X2_df[col], y2)
        split_corrs["period_1"][col] = round(r1, 4)
        split_corrs["period_2"][col] = round(r2, 4)
    results["split_correlations"] = split_corrs

    # 5. Chow test at t=100
    X1_with_const = np.column_stack([np.ones(mid), X1_df.values])
    X2_with_const = np.column_stack([np.ones(n - mid), X2_df.values])
    f_stat, p_val = chow_test(y, X1_with_const, X2_with_const)
    results["chow_test"] = {
        "breakpoint": mid,
        "f_statistic": f_stat,
        "p_value": p_val,
        "significant_at_005": bool(p_val < 0.05),
    }

    # 6. Rolling-window correlations (window=50)
    window = 50
    rolling = {}
    for col in feature_cols[:5]:
        corrs_over_time = []
        for start in range(0, n - window + 1, 10):
            end = start + window
            r, _ = stats.pearsonr(X[col].iloc[start:end], y[start:end])
            corrs_over_time.append({"t_start": start, "r": round(r, 4)})
        rolling[col] = corrs_over_time
    results["rolling_correlations"] = rolling

    # 7. Lasso on each half
    lasso1 = LassoCV(cv=5, random_state=42, max_iter=10000).fit(X1_df, y1)
    lasso2 = LassoCV(cv=5, random_state=42, max_iter=10000).fit(X2_df, y2)
    results["lasso_split"] = {
        "period_1": {
            "alpha": round(lasso1.alpha_, 6),
            "selected": [f for f, c in zip(feature_cols, lasso1.coef_) if abs(c) > 0.01],
        },
        "period_2": {
            "alpha": round(lasso2.alpha_, 6),
            "selected": [f for f, c in zip(feature_cols, lasso2.coef_) if abs(c) > 0.01],
        },
    }

    # 8. Random Forest on full sample
    rf = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
    rf.fit(X, y)
    rf_cv = cross_val_score(rf, X, y, cv=5, scoring="r2", n_jobs=-1).mean()
    importances = dict(zip(feature_cols, np.round(rf.feature_importances_, 4)))
    results["random_forest"] = {
        "cv_r2": round(rf_cv, 4),
        "importances": importances,
        "top_features": sorted(importances, key=importances.get, reverse=True)[:5],
    }

    # 9. Y mean/std by half
    results["y_by_half"] = {
        "period_1": {"mean": round(float(y1.mean()), 4), "std": round(float(y1.std()), 4)},
        "period_2": {"mean": round(float(y2.mean()), 4), "std": round(float(y2.std()), 4)},
    }

    return results


def main():
    os.makedirs("results", exist_ok=True)

    print("=" * 60)
    print("HIDDEN BREAKPOINT — BASELINE ANALYSIS")
    print("=" * 60)

    for label, path in [
        ("breakpoint_live", "breakpoint_live_data.csv"),
        ("breakpoint_dead", "breakpoint_dead_data.csv"),
    ]:
        print(f"\n--- {label.upper()} ---")
        results = analyze_dataset(path, label)

        with open(f"results/baseline_{label}.json", "w") as f:
            json.dump(results, f, indent=2)

        print(f"  Pooled OLS R²: {results['pooled_ols']['r2']}")
        print(f"  Pooled sig (Bonferroni): {[f for f, p in results['pooled_corr_pvalues'].items() if p < 0.05/10]}")
        print(f"  Split period 1 R²: {results['split_ols']['period_1']['r2']}")
        print(f"  Split period 2 R²: {results['split_ols']['period_2']['r2']}")
        print(f"  Chow test F={results['chow_test']['f_statistic']}, p={results['chow_test']['p_value']}")
        print(f"  Chow significant: {results['chow_test']['significant_at_005']}")
        print(f"  Lasso period 1: {results['lasso_split']['period_1']['selected']}")
        print(f"  Lasso period 2: {results['lasso_split']['period_2']['selected']}")
        print(f"  RF CV R²: {results['random_forest']['cv_r2']}")
        print(f"  Y by half: {results['y_by_half']}")

    print("\nBaseline analysis complete.")


if __name__ == "__main__":
    main()
