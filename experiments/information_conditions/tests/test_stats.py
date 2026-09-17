import json

import numpy as np
import pandas as pd
import pytest

from infocond import data, stats
from infocond.paths import REPO_ROOT


@pytest.fixture(scope="module")
def live(cfg, datasets_ready):
    return data.load_dataset(cfg, "live_salmon")


def test_ols_r2_matches_committed_baseline(cfg, datasets_ready):
    for name in ("live_salmon", "dead_salmon"):
        df = data.load_dataset(cfg, name)
        res = stats.ols_with_intercept(df[stats.FEATURE_NAMES].to_numpy(), df["Y"].to_numpy())
        base = json.loads((REPO_ROOT / f"results/baseline_{name}.json").read_text())
        assert round(res.r2, 4) == base["ols"]["r2"]
        assert res.n == 1000 and res.p == 20 and len(res.beta) == 21


def test_ols_residual_properties(live):
    X = live[stats.FEATURE_NAMES].to_numpy()
    y = live["Y"].to_numpy()
    res = stats.ols_with_intercept(X, y)
    # residuals orthogonal to intercept and every predictor; fitted + residual = y
    assert abs(res.residuals.mean()) < 1e-10
    assert np.max(np.abs(X.T @ res.residuals)) < 1e-8
    assert np.allclose(res.fitted + res.residuals, y)
    # R^2 equals the squared correlation between y and fitted values for OLS with intercept
    assert abs(res.r2 - stats.pearson(y, res.fitted) ** 2) < 1e-10
    # normal-equation solution agrees with lstsq
    D = np.column_stack([np.ones(len(y)), X])
    beta_ne = np.linalg.solve(D.T @ D, D.T @ y)
    assert np.allclose(beta_ne, res.beta, atol=1e-8)


def test_ols_rejects_bad_shapes():
    with pytest.raises(ValueError):
        stats.ols_with_intercept(np.zeros((5, 2)), np.zeros(4))


def test_residual_square_correlations_definition(live):
    X = live[stats.FEATURE_NAMES].to_numpy()
    y = live["Y"].to_numpy()
    res = stats.ols_with_intercept(X, y)
    diag = stats.residual_square_correlations(res.residuals, X, stats.FEATURE_NAMES)
    assert [n for n, _ in diag] == stats.FEATURE_NAMES
    assert len(diag) == 20
    e2 = res.residuals ** 2
    for k, (name, r) in enumerate(diag):
        expected = np.corrcoef(e2, X[:, k] ** 2)[0, 1]
        assert abs(r - expected) < 1e-12
    # it is corr(e^2, Xi^2), not corr(e^2, Xi): the two must differ for the live data
    r_lin = np.corrcoef(e2, X[:, 3])[0, 1]
    assert abs(diag[3][1] - r_lin) > 1e-3


def test_second_order_terms_count_uniqueness_order():
    terms = stats.second_order_terms(stats.FEATURE_NAMES)
    names = [t for _, _, t in terms]
    assert len(terms) == 210 and len(set(names)) == 210
    assert sum(1 for a, b, _ in terms if a == b) == 20
    assert sum(1 for a, b, _ in terms if a != b) == 190
    # fixed numeric-index order: (1,1),(1,2),...,(1,20),(2,2),...
    idx = [(int(a[1:]), int(b[1:])) for a, b, _ in terms]
    assert idx == sorted(idx)
    assert idx[0] == (1, 1) and idx[1] == (1, 2) and idx[20] == (2, 2) and idx[-1] == (20, 20)
    assert names[0] == "X1^2" and names[1] == "X1*X2" and names[-1] == "X20^2"
    assert all(int(a[1:]) < int(b[1:]) for a, b, t in terms if "*" in t)


def test_second_order_correlations_definition(live):
    rows = stats.second_order_correlations(live[stats.FEATURE_NAMES], live["Y"].to_numpy(), stats.FEATURE_NAMES)
    assert len(rows) == 210 and all(n == 1000 for _, _, n in rows)
    d = dict((t, r) for t, r, _ in rows)
    prod = live["X4"] * live["X5"]
    assert abs(d["X4*X5"] - np.corrcoef(live["Y"], prod)[0, 1]) < 1e-12
    sq = live["X7"] ** 2
    assert abs(d["X7^2"] - np.corrcoef(live["Y"], sq)[0, 1]) < 1e-12
    # symmetric product: value is the same whichever order, only one row is emitted
    assert "X5*X4" not in d


def test_format_number_and_table():
    assert stats.format_number(-0.00001, 4) == "0.0000"
    assert stats.format_number(0.12345, 4) == "0.1235"  # round-half-even on binary repr; deterministic
    t = stats.format_table(["a", "bb"], [["1", "2"], ["333", "4"]])
    assert t.splitlines()[0].startswith("a")
    assert len(t.splitlines()) == 4
    with pytest.raises(ValueError):
        stats.format_table(["a"], [["1", "2"]])
