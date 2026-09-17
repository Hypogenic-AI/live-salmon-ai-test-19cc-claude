"""Build the three information conditions and the full prompt bundles.

A        : upstream prepare_summary() output, unchanged.
A_prime  : A + supplied OLS diagnostics (R^2, n, corr(e^2, Xi^2) for X1..X20).
B        : A_prime + Pearson r of Y with all 210 second-order terms.

The system prompt and user template are the upstream ones for every condition;
only the data summary inserted into the template differs.
"""
from __future__ import annotations

import math
import re

import pandas as pd

from .common import sha256_text
from .data import dataset_path, load_dataset
from .stats import (FEATURE_NAMES, format_number, format_table, ols_with_intercept,
                    residual_square_correlations, second_order_correlations, second_order_terms)
from . import upstream

CONDITIONS = ("A", "A_prime", "B")
DATASET_ORDER = ("live_salmon", "dead_salmon")

# Content that must never appear in any model input.  Plain substrings cover
# dataset identities and answer-key vocabulary; anchored regexes cover the true
# generating formula in several notations (a bare substring like "2*x1" would
# collide with legitimate table rows such as "X12*X13").
FORBIDDEN_SUBSTRINGS = [
    "salmon", "live_", "dead_", "live data", "dead data", "null data", "ground truth", "ground_truth",
    "true formula", "true_formula", "answer key", "generating formula", "data generating process is",
    "+ epsilon", "n(0,1)", "n(0, 1)", "interaction_term", "true_coefficients",
    "correlated_non_causal", "noise_distractor", "truly_predictive",
]
_MUL = r"\s*[\*·×]\s*"
FORBIDDEN_PATTERNS = {
    "2*X1 (true coefficient)": re.compile(r"(?<![\d.])2(?:\.0+)?" + _MUL + r"\(?x1(?!\d)", re.I),
    "0.5*X2 (true coefficient)": re.compile(r"(?<![\d.])0?\.50*" + _MUL + r"\(?x2(?!\d)", re.I),
    "1.5*X3 (true coefficient)": re.compile(r"(?<![\d.])1\.50*" + _MUL + r"\(?x3(?!\d)", re.I),
    "0.8*X4*X5 (true interaction)": re.compile(r"(?<![\d.])0?\.80*" + _MUL + r"\(?\s*x4" + _MUL + r"x5", re.I),
    "coefficient-style X4*X5 formula": re.compile(r"[-+]?\d+(?:\.\d+)?" + _MUL + r"\(\s*x4" + _MUL + r"x5\s*\)", re.I),
}


def forbidden_content_hits(text: str) -> list[str]:
    low = text.lower()
    hits = [s for s in FORBIDDEN_SUBSTRINGS if s in low]
    hits += [name for name, pat in FORBIDDEN_PATTERNS.items() if pat.search(text)]
    return hits


class InputTooLong(RuntimeError):
    pass


class ForbiddenContent(RuntimeError):
    pass


def estimate_tokens(text: str, chars_per_token: float) -> int:
    return int(math.ceil(len(text) / chars_per_token))


# ---------------------------------------------------------------------------
# Appended sections
# ---------------------------------------------------------------------------

def build_supplied_stats_part1(df: pd.DataFrame, decimals: int) -> tuple[str, dict]:
    X = df[FEATURE_NAMES].to_numpy(dtype=float)
    y = df["Y"].to_numpy(dtype=float)
    res = ols_with_intercept(X, y)
    diag = residual_square_correlations(res.residuals, X, FEATURE_NAMES)
    if len(diag) != len(FEATURE_NAMES):
        raise RuntimeError("expected one residual diagnostic per predictor")
    n = res.n
    r2 = format_number(res.r2, decimals)
    rows = [[name, format_number(r, decimals), str(n)] for name, r in diag]
    table = format_table(["Predictor", "corr(e^2, Xi^2)", "n"], rows)
    text = f"""
## Supplied Precomputed Statistics, Part 1: Linear-fit diagnostics
The statistics in this section were precomputed on the complete dataset and are supplied to you as given inputs; you did not compute them and you cannot request others.

How they were computed: An ordinary least squares (OLS) regression of Y on all {len(FEATURE_NAMES)} predictors X1-X{len(FEATURE_NAMES)}, including an intercept term, was fitted using all n = {n} observations. The in-sample coefficient of determination (R^2) of that fit was recorded. The residual of each observation, e = Y - Yhat (observed minus fitted value), was squared, and for every predictor Xi the Pearson correlation between the squared residual e^2 and the squared predictor Xi^2 was computed across the same n observations. Fitted coefficients from this regression are not supplied.

- Sample size used for the OLS fit: n = {n}
- In-sample R^2 of the OLS fit (intercept + X1-X{len(FEATURE_NAMES)}): {r2}

Table 1. Pearson correlation between the squared OLS residual e^2 and each squared predictor Xi^2 ({len(rows)} rows, fixed index order).
{table}
"""
    details = {
        "ols_n": n,
        "ols_r2": res.r2,
        "ols_r2_rounded": r2,
        "n_residual_diagnostics": len(diag),
        "residual_square_correlations": {name: r for name, r in diag},
        # kept for evaluation only; never written into prompts
        "_fitted_coefficients_not_in_prompt": {name: float(b) for name, b in zip(["intercept"] + FEATURE_NAMES, res.beta)},
    }
    return text, details


def build_supplied_stats_part2(df: pd.DataFrame, decimals: int) -> tuple[str, dict]:
    X = df[FEATURE_NAMES]
    y = df["Y"].to_numpy(dtype=float)
    rows_raw = second_order_correlations(X, y, FEATURE_NAMES)
    terms = second_order_terms(FEATURE_NAMES)
    n_sq = sum(1 for a, b, _ in terms if a == b)
    n_cross = len(terms) - n_sq
    if len(rows_raw) != 210 or n_sq != 20 or n_cross != 190:
        raise RuntimeError(f"expected 210 terms (20 squares + 190 cross products), got {len(rows_raw)}")
    if len({t for t, _, _ in rows_raw}) != len(rows_raw):
        raise RuntimeError("duplicate term names")
    n = int(rows_raw[0][2])
    rows = [[term, format_number(r, decimals), str(nn)] for term, r, nn in rows_raw]
    table = format_table(["Term", "r", "n"], rows)
    text = f"""
## Supplied Precomputed Statistics, Part 2: Correlations of Y with second-order terms
The statistics in this section were precomputed on the complete dataset and are supplied to you as given inputs.

How they were computed: For every pair of predictors (Xi, Xj) with i <= j, a second-order term was formed row by row from the raw (uncentered) predictor values: the {n_sq} squared terms Xi^2 (where i = j) and the {n_cross} distinct cross-product terms Xi*Xj (where i < j), {len(rows)} terms in total. The Pearson correlation r between Y and each term was computed across all n = {n} observations. The table lists every term in fixed index order (by i, then by j); it is not sorted by correlation and nothing has been filtered out. Values are raw Pearson r. No p-values, significance markers, adjustments for multiple comparisons, or selected subsets are supplied.

Table 2. Pearson correlation of Y with each second-order term ({len(rows)} rows: {n_sq} squares, {n_cross} cross products).
{table}
"""
    details = {
        "n_second_order_terms": len(rows_raw),
        "n_squares": n_sq,
        "n_cross_products": n_cross,
        "n": n,
        "second_order_correlations": {term: r for term, r, _ in rows_raw},
    }
    return text, details


# ---------------------------------------------------------------------------
# Condition assembly
# ---------------------------------------------------------------------------

def build_summary(condition: str, csv_path: str, label: str, decimals: int) -> tuple[str, dict]:
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition {condition!r}")
    base = upstream.prepare_summary(csv_path, label)
    details: dict = {"base_summary_sha256": sha256_text(base), "base_summary_chars": len(base)}
    if condition == "A":
        return base, details
    df = pd.read_csv(csv_path)
    text = base
    part1, d1 = build_supplied_stats_part1(df, decimals)
    text += part1
    details.update(d1)
    if condition == "B":
        part2, d2 = build_supplied_stats_part2(df, decimals)
        text += part2
        details.update(d2)
    return text, details


def build_bundle(condition: str, dataset_key: str, cfg: dict) -> dict:
    ds = cfg["datasets"][dataset_key]
    csv_path = str(dataset_path(cfg, dataset_key))
    summary, details = build_summary(condition, csv_path, ds["label"], cfg["decimals"])
    system = upstream.system_prompt()
    user = upstream.user_prompt_template().format(data_summary=summary)
    hits = forbidden_content_hits(system + "\n" + user)
    if hits:
        raise ForbiddenContent(f"{dataset_key}/{condition}: forbidden content in prompt: {hits}")
    cpt = cfg["input_length"]["chars_per_token_conservative"]
    combined = system + "\n" + user
    public_details = {k: v for k, v in details.items() if not k.startswith("_")}
    return {
        "dataset": dataset_key,
        "condition": condition,
        "dataset_label_in_prompt": ds["label"],
        "system_prompt": system,
        "user_prompt": user,
        "summary": summary,
        "hashes": {
            "system_prompt_sha256": sha256_text(system),
            "user_prompt_sha256": sha256_text(user),
            "combined_sha256": sha256_text(combined),
            "summary_sha256": sha256_text(summary),
        },
        "chars": {"system": len(system), "user": len(user), "combined": len(combined)},
        "estimated_input_tokens": estimate_tokens(combined, cpt),
        "details": public_details,
        "_private_details": {k: v for k, v in details.items() if k.startswith("_")},
    }


def check_input_length(bundle: dict, cfg: dict) -> dict:
    limit = cfg["input_length"]["max_estimated_input_tokens"]
    est = bundle["estimated_input_tokens"]
    result = {"estimated_input_tokens": est, "limit": limit, "ok": est <= limit,
              "method": f"ceil(chars / {cfg['input_length']['chars_per_token_conservative']})"}
    if not result["ok"]:
        raise InputTooLong(f"{bundle['dataset']}/{bundle['condition']}: estimated {est} tokens > limit {limit}")
    return result


def build_all_bundles(cfg: dict) -> list[dict]:
    bundles = []
    for dataset_key in DATASET_ORDER:
        for condition in cfg["conditions"]:
            b = build_bundle(condition, dataset_key, cfg)
            check_input_length(b, cfg)
            bundles.append(b)
    systems = {b["hashes"]["system_prompt_sha256"] for b in bundles}
    if len(systems) != 1:
        raise RuntimeError("system prompt must be identical across all conditions")
    return bundles


def input_basename(dataset_key: str, condition: str) -> str:
    return f"{dataset_key}__{condition}"
