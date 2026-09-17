"""Statistics used by conditions A_prime and B.

Only numpy is required.  Everything is computed on the full dataset, with fixed
numeric-index ordering, and rendered without truncation.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

FEATURE_NAMES = [f"X{i}" for i in range(1, 21)]


@dataclass
class OLSResult:
    beta: np.ndarray          # intercept first, then one coefficient per predictor
    fitted: np.ndarray
    residuals: np.ndarray
    r2: float
    n: int
    p: int                    # number of predictors (excluding intercept)


def ols_with_intercept(X: np.ndarray, y: np.ndarray) -> OLSResult:
    """Ordinary least squares of y on [1, X] using all observations."""
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    if X.ndim != 2 or y.ndim != 1 or X.shape[0] != y.shape[0]:
        raise ValueError("X must be (n, p) and y must be (n,) with matching n")
    n, p = X.shape
    design = np.column_stack([np.ones(n), X])
    beta, _, rank, _ = np.linalg.lstsq(design, y, rcond=None)
    if rank < p + 1:
        raise ValueError(f"design matrix is rank deficient (rank {rank} < {p + 1})")
    fitted = design @ beta
    resid = y - fitted
    ss_res = float(resid @ resid)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot
    return OLSResult(beta=beta, fitted=fitted, residuals=resid, r2=r2, n=n, p=p)


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a = a - a.mean()
    b = b - b.mean()
    denom = np.sqrt((a @ a) * (b @ b))
    if denom == 0:
        raise ValueError("zero variance in pearson()")
    return float((a @ b) / denom)


def residual_square_correlations(residuals: np.ndarray, X: np.ndarray, names: list[str]) -> list[tuple[str, float]]:
    """corr(e^2, Xi^2) for every predictor, in the given (numeric-index) order."""
    e2 = np.asarray(residuals, dtype=float) ** 2
    X = np.asarray(X, dtype=float)
    if X.shape[1] != len(names):
        raise ValueError("names must match the number of predictor columns")
    return [(name, pearson(e2, X[:, k] ** 2)) for k, name in enumerate(names)]


def second_order_terms(names: list[str]) -> list[tuple[str, str, str]]:
    """All (Xi, Xj) with i <= j in fixed index order: squares are 'Xi^2', cross
    products are 'Xi*Xj'.  For 20 predictors this yields 20 + 190 = 210 terms."""
    out = []
    for i, a in enumerate(names):
        for j in range(i, len(names)):
            b = names[j]
            term = f"{a}^2" if i == j else f"{a}*{b}"
            out.append((a, b, term))
    return out


def second_order_correlations(X: pd.DataFrame, y: np.ndarray, names: list[str]) -> list[tuple[str, float, int]]:
    """Pearson r between y and each second-order term built row-wise from the raw
    (uncentred) predictor values.  Returns (term, r, n) in fixed index order."""
    y = np.asarray(y, dtype=float)
    n = len(y)
    rows = []
    for a, b, term in second_order_terms(names):
        prod = X[a].to_numpy(dtype=float) * X[b].to_numpy(dtype=float)
        rows.append((term, pearson(y, prod), n))
    return rows


def format_number(x: float, decimals: int) -> str:
    s = f"{x:.{decimals}f}"
    if s.startswith("-") and float(s) == 0.0:   # avoid '-0.0000'
        s = s[1:]
    return s


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Fixed-width, left-aligned text table.  Never truncates rows."""
    widths = [len(h) for h in headers]
    for r in rows:
        if len(r) != len(headers):
            raise ValueError("row length mismatch")
        for k, cell in enumerate(r):
            widths[k] = max(widths[k], len(cell))
    fmt = "  ".join("{:<" + str(w) + "}" for w in widths)
    lines = [fmt.format(*headers).rstrip(), fmt.format(*["-" * w for w in widths]).rstrip()]
    lines += [fmt.format(*r).rstrip() for r in rows]
    return "\n".join(lines)
