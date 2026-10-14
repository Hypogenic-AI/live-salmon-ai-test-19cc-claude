"""
Offline checks on the lab world: it reproduces the original study when nothing is set,
interventions behave like interventions, the analysis tools are correct, and the
prediction questions separate the truth from the traps.

Run from the repository root:  uv run --with pytest pytest experiments/salmon_lab -q
"""

import numpy as np
import pytest

from world import NAMES, LabWorld, fit_ols, questions


def big_world(seed=0):
    return LabWorld(seed, run_budget=100_000, max_runs_per_turn=100_000)


def coef(fit, term):
    return next(c["estimate"] for c in fit["coefficients"] if c["term"] == term)


def test_nothing_set_reproduces_the_original_study():
    w = big_world()
    w.run_experiments([{"n": 5000}])
    X, y = w.matrix()
    assert np.corrcoef(X[:, 0], X[:, 15])[0, 1] == pytest.approx(0.919, abs=0.02)  # X1 with its proxy X16
    assert np.corrcoef(X[:, 3], y)[0, 1] == pytest.approx(0, abs=0.04)  # X4 alone looks unrelated to Y
    fit = fit_ols(X, y, "Y ~ X1 + X2 + X3 + X4 + X5 + X4:X5")
    for term, value in [("X1", 2), ("X2", 0.5), ("X3", -1.5), ("X4", 0), ("X5", 0), ("X4:X5", 0.8)]:
        assert coef(fit, term) == pytest.approx(value, abs=0.1)


def test_setting_a_proxy_cuts_its_link():
    w = big_world()
    w.run_experiments([{"set": {"X16": 2}, "n": 2000}])
    _, y = w.matrix()
    assert abs(y.mean()) < 0.25  # X16 has no effect once it is set by hand


def test_setting_a_cause_moves_its_proxy():
    w = big_world()
    w.run_experiments([{"set": {"X1": 2}, "n": 2000}])
    X, _ = w.matrix()
    assert X[:, 15].mean() == pytest.approx(1.4, abs=0.05)  # X16 = 0.7 X1 + noise


def test_one_at_a_time_with_x5_at_zero_misses_x4():
    w = big_world()
    w.run_experiments([{"set": {"X4": v, "X5": 0}, "n": 200} for v in (-3, -1.5, 0, 1.5, 3)])
    X, y = w.matrix()
    assert abs(coef(fit_ols(X, y, "Y ~ X4"), "X4")) < 0.15


def test_two_by_two_design_reveals_the_interaction():
    w = big_world()
    w.run_experiments([{"set": {"X4": a, "X5": b}, "n": 50} for a in (-2, 2) for b in (-2, 2)])
    X, y = w.matrix()
    assert coef(fit_ols(X, y, "Y ~ X4 + X5 + X4:X5"), "X4:X5") == pytest.approx(0.8, abs=0.1)


def test_fit_recovers_known_coefficients_exactly():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(50, 20))
    y = 1 + 2 * X[:, 0] - 3 * X[:, 1] * X[:, 2] + 0.5 * X[:, 4] ** 2
    fit = fit_ols(X, y, "Y ~ X1 + X2:X3 + X5^2")
    assert coef(fit, "Intercept") == pytest.approx(1, abs=1e-6)
    assert coef(fit, "X1") == pytest.approx(2, abs=1e-6)
    assert coef(fit, "X2:X3") == pytest.approx(-3, abs=1e-6)
    assert coef(fit, "X5^2") == pytest.approx(0.5, abs=1e-6)


def test_fit_matches_textbook_standard_errors():
    rng = np.random.default_rng(2)
    X = rng.normal(size=(40, 20))
    y = X[:, 0] + rng.normal(size=40)
    fit = fit_ols(X, y, "Y ~ X1 + X2")
    D = np.column_stack([np.ones(40), X[:, 0], X[:, 1]])
    beta = np.linalg.solve(D.T @ D, D.T @ y)
    sigma2 = ((y - D @ beta) ** 2).sum() / (40 - 3)
    se = np.sqrt(sigma2 * np.diag(np.linalg.inv(D.T @ D)))
    assert [c["se"] for c in fit["coefficients"]] == pytest.approx(se, abs=1e-4)


def test_fit_flags_terms_that_cannot_be_separated():
    w = big_world()
    w.run_experiments([{"set": {"X4": 2}, "n": 60}])  # X4 never varies
    X, y = w.matrix()
    fit = fit_ols(X, y, "Y ~ X4 + X5 + X4:X5")
    assert coef(fit, "X4") is None  # same as the intercept in these runs
    assert coef(fit, "X5") == pytest.approx(1.6, abs=0.2)  # 0.8 * 2
    assert coef(fit, "X4:X5") is None  # 2 * X5, the same as X5


@pytest.mark.parametrize("formula", ["Y ~ X21", "Y ~ foo", "Z ~ X1", "Y ~ ", "X1 + X2", 7])
def test_fit_rejects_bad_formulas(formula):
    with pytest.raises(ValueError):
        fit_ols(np.zeros((30, 20)), np.zeros(30), formula)


def test_limits_and_bad_requests():
    w = LabWorld(0, run_budget=150, max_runs_per_turn=100)
    rows, msgs = w.run_experiments([{"n": 80}, {"set": {"X1": 1}, "n": 40}])
    assert len(rows) == 100 and any("only 20 of 40" in m for m in msgs)
    rows, msgs = w.run_experiments([{"n": 100}])
    assert len(rows) == 50 and w.runs_left() == 0
    bad = [{"set": {"X1": 5}}, {"set": {"X99": 1}}, {"n": 0}, {"fly": 1}, {"set": {"X1": True}}, {"n": True}]
    rows, msgs = LabWorld(0).run_experiments(bad)
    assert rows == [] and len(msgs) == len(bad)
    assert LabWorld(0).run_experiments({"n": 5}) == ([], ["Experiments must be a JSON array."])


def test_analyses_and_their_errors():
    w = LabWorld(0)
    assert "error" in w.analyse([{"fit": "Y ~ X1"}])[0]  # no data yet
    w.run_experiments([{"n": 40}, {"set": {"X1": 2}, "n": 10}])
    out = w.analyse([
        {"fit": "Y ~ X1"},
        {"fit": "Y ~ bad"},
        {"correlations": ["X1", "Y"]},
        {"summary": ["X1", "Y"], "runs": [41, 50]},
        {"summary": "X1"},
        {"correlations": ["X1"], "runs": [1, 99]},
        {"what": 1},
        {"fit": "Y ~ X1", "summary": ["Y"]},
        "fit",
    ])
    assert "coefficients" in out[0] and out[0]["runs"] == [1, 50]
    assert out[2]["correlations"]["X1"]["X1"] == 1.0
    assert out[3]["summary"]["X1"] == {"mean": 2.0, "sd": 0.0, "min": 2.0, "max": 2.0}
    assert [("error" in o) for o in out] == [False, True, False, False, True, True, True, True, True]
    assert len(w.analysis_log) == 1 + len(out)


def test_questions_have_true_and_trap_answers():
    qs = {q["text"]: q for q in questions()}
    assert qs["all features at 0"]["true"] == 0
    assert qs["X4 = 2, X5 = 2"]["true"] == pytest.approx(3.2) and qs["X4 = 2, X5 = 2"]["trap"] == 0
    assert qs["X16 = 2"]["true"] == 0 and qs["X16 = 2"]["trap"] == pytest.approx(4.83, abs=0.01)
    assert qs["X4 = 3"]["true"] == 0 == qs["X4 = 3"]["trap"]
    assert sum(q["kind"] in ("interaction", "proxy") for q in questions()) == 6


def test_evidence_is_there_in_passive_data():
    w = big_world(2)
    w.run_experiments([{"n": 100}])
    ev = w.evidence()
    assert ev["identifiable"] and ev["x4x5_rank"] == 1
    assert ev["x4x5_estimate"] == pytest.approx(0.8, abs=0.25)


def test_evidence_is_absent_after_one_at_a_time_with_the_rest_at_zero():
    w = big_world(3)
    w.run_experiments([{"set": {n: (x if n == v else 0) for n in NAMES}, "n": 7} for v in NAMES for x in (-2, 2)])
    ev = w.evidence()
    assert not ev["x4x5_estimable"] and not ev["identifiable"]


def test_evidence_with_too_few_runs():
    w = big_world()
    w.run_experiments([{"n": 15}])
    assert w.evidence()["identifiable"] is False
