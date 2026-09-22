"""Numerical and isolation checks for the discovery-only analysis tools.

The references below fit explicit design matrices with scikit-learn rather than
calling the analysis module's feature construction or scoring helpers.
"""

import copy
import itertools
import unittest

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import KFold

from experiments.adaptive_analysis.analysis import AnalysisSession
from src.baseline_analysis import fit_ols


def gated_data(seed=31):
    """Balanced independent features make the marginal interaction exactly half.

    Each gate is equally represented for every pair of values of X1 and X2.
    This avoids making the signal-recovery assertion depend on a lucky sample.
    """
    values = np.array(list(itertools.product((-1.0, 1.0), repeat=4)))
    values = np.repeat(values, 12, axis=0)
    rng = np.random.default_rng(seed)
    rng.shuffle(values)
    frame = pd.DataFrame(values, columns=["X1", "X2", "X3", "X4"])
    frame["Y"] = (
        0.4
        + 1.5 * frame["X1"]
        - 0.7 * frame["X2"]
        + 1.13 * frame["X1"] * frame["X2"] * (frame["X3"] > 0)
        + rng.normal(0, 0.005, len(frame))
    )
    return frame


def independent_design(frame, kind):
    columns = [frame[name].to_numpy() for name in ("X1", "X2", "X3", "X4")]
    if kind in {"interaction", "conditional"}:
        columns.append(frame["X1"].to_numpy() * frame["X2"].to_numpy())
    if kind == "conditional":
        columns.append(columns[-1] * (frame["X3"].to_numpy() > 0))
    return np.column_stack(columns)


class AnalysisSessionTests(unittest.TestCase):
    def setUp(self):
        self.frame = gated_data()
        self.session = AnalysisSession(self.frame, seed=17, folds=3, top_k=3)

    def test_linear_and_null_match_independent_estimators(self):
        linear = self.session.fit_model({"kind": "linear"})
        null = self.session.fit_model({"kind": "null"})
        features = self.frame.drop(columns="Y")
        reference = LinearRegression().fit(features, self.frame["Y"])
        np.testing.assert_allclose(
            self.session.predict(linear["model_id"], features),
            reference.predict(features),
            rtol=1e-10,
            atol=1e-10,
        )
        np.testing.assert_allclose(
            self.session.predict(null["model_id"], features),
            np.full(len(features), self.frame["Y"].mean()),
            rtol=1e-10,
            atol=1e-10,
        )
        target = self.frame["Y"].to_numpy()
        expected_null_mse = [
            np.mean((target[validation] - target[train].mean()) ** 2)
            for train, validation in KFold(n_splits=3, shuffle=True, random_state=17).split(features)
        ]
        np.testing.assert_allclose(null["fold_mse"], expected_null_mse, atol=1e-12)

    def test_conditional_fit_matches_explicit_global_and_gated_design(self):
        spec = {"kind": "conditional", "pair": ["X1", "X2"], "gate": "X3"}
        conditional = self.session.fit_model(spec)
        interaction = self.session.fit_model({"kind": "interaction", "pair": ["X1", "X2"]})
        design = independent_design(self.frame, "conditional")
        reference = LinearRegression().fit(design, self.frame["Y"])
        global_reference = LinearRegression().fit(
            independent_design(self.frame, "interaction"), self.frame["Y"]
        )
        self.assertAlmostEqual(reference.coef_[-2], 0.0, delta=0.01)
        self.assertAlmostEqual(reference.coef_[-2] + reference.coef_[-1], 1.13, delta=0.01)
        self.assertAlmostEqual(global_reference.coef_[-1], 1.13 / 2, delta=0.01)
        self.assertAlmostEqual(conditional["coefficients"]["X1*X2"], reference.coef_[-2])
        self.assertAlmostEqual(conditional["coefficients"]["X1*X2|X3>0"], reference.coef_[-1])
        self.assertAlmostEqual(conditional["group_slopes"]["nonpositive"], 0.0, delta=0.01)
        self.assertAlmostEqual(conditional["group_slopes"]["positive"], 1.13, delta=0.01)
        self.assertAlmostEqual(interaction["coefficients"]["X1*X2"], 1.13 / 2, delta=0.01)
        self.assertLess(conditional["cv_mse"], interaction["cv_mse"] / 100)
        np.testing.assert_allclose(
            self.session.predict(conditional["model_id"], self.frame.drop(columns="Y")),
            reference.predict(design),
            rtol=1e-10,
            atol=1e-10,
        )
        boundary_probes = pd.DataFrame({
            "X1": [1.0, 1.0, 1.0], "X2": [1.0, 1.0, 1.0],
            "X3": [-0.1, 0.0, 0.1], "X4": [0.0, 0.0, 0.0],
        })
        np.testing.assert_allclose(
            self.session.predict(conditional["model_id"], boundary_probes),
            reference.predict(independent_design(boundary_probes, "conditional")),
            atol=1e-10,
        )

    def test_cv_matches_fits_on_training_folds_and_is_reproducible(self):
        spec = {"kind": "conditional", "pair": ["X1", "X2"], "gate": "X3"}
        record = self.session.fit_model(spec)
        design = independent_design(self.frame, "conditional")
        target = self.frame["Y"].to_numpy()
        expected = []
        for train, validation in KFold(n_splits=3, shuffle=True, random_state=17).split(design):
            reference = LinearRegression().fit(design[train], target[train])
            expected.append(float(np.mean((target[validation] - reference.predict(design[validation])) ** 2)))
        np.testing.assert_allclose(record["fold_mse"], expected, rtol=1e-10, atol=1e-12)
        self.assertAlmostEqual(record["cv_mse"], np.mean(expected), places=12)
        self.assertAlmostEqual(record["cv_mse_se"], np.std(expected, ddof=1) / np.sqrt(3), places=12)

        another = AnalysisSession(self.frame, seed=17, folds=3, top_k=3)
        other_record = another.fit_model(spec)
        for key in ("model_id", "spec", "cv_mse", "fold_mse", "coefficients"):
            self.assertEqual(record[key], other_record[key])

    def test_cache_and_holdout_predictions_do_not_refit_or_change_evidence(self):
        spec = {"kind": "conditional", "pair": ["X1", "X2"], "gate": "X3"}
        before = copy.deepcopy(self.session.stats)
        record = self.session.fit_model(spec)
        self.assertEqual(self.session.stats["candidate_models"] - before["candidate_models"], 1)
        self.assertEqual(self.session.stats["cv_fits"] - before["cv_fits"], 3)
        self.assertEqual(self.session.stats["final_fits"] - before["final_fits"], 1)
        fitted_stats = copy.deepcopy(self.session.stats)
        repeated = self.session.fit_model(copy.deepcopy(spec))
        self.assertEqual(record, repeated)
        for key in ("candidate_models", "cv_fits", "final_fits"):
            self.assertEqual(self.session.stats[key], fitted_stats[key])
        self.assertEqual(self.session.stats["cache_hits"], fitted_stats["cache_hits"] + 1)

        stats_before_predict = copy.deepcopy(self.session.stats)
        records_before_predict = copy.deepcopy(self.session.records)
        exposed_before_predict = (
            set(self.session.exposed_model_ids), set(self.session.evidence_ids)
        )
        heldout = gated_data(seed=93).drop(columns="Y")
        predictions = self.session.predict(record["model_id"], heldout)
        reference = LinearRegression().fit(independent_design(self.frame, "conditional"), self.frame["Y"])
        np.testing.assert_allclose(
            predictions, reference.predict(independent_design(heldout, "conditional")), atol=1e-10
        )
        self.assertEqual(self.session.stats, stats_before_predict)
        self.assertEqual(self.session.records, records_before_predict)
        self.assertEqual(
            (set(self.session.exposed_model_ids), set(self.session.evidence_ids)),
            exposed_before_predict,
        )
        with self.assertRaises(ValueError):
            self.session.predict(record["model_id"], gated_data(seed=93))

    def test_discovery_frame_is_copied_and_invalid_models_do_not_spend_fits(self):
        original = self.frame.copy(deep=True)
        self.frame.loc[:, "Y"] = -999.0
        self.frame.loc[:, "X1"] = 999.0
        record = self.session.fit_model({"kind": "linear"})
        reference = LinearRegression().fit(original.drop(columns="Y"), original["Y"])
        np.testing.assert_allclose(
            self.session.predict(record["model_id"], original.drop(columns="Y")),
            reference.predict(original.drop(columns="Y")),
            atol=1e-10,
        )
        after_external_mutation = self.frame.copy(deep=True)
        invalid_specs = [
            {"kind": "unknown"},
            {"kind": "interaction", "pair": ["X1", "missing"]},
            {"kind": "interaction", "pair": ["X1", "X1"]},
            {"kind": "interaction", "pair": ["X1"]},
            {"kind": "conditional", "pair": ["X1", "X2"], "gate": "X1"},
            {"kind": "conditional", "pair": ["X1", "X2"], "gate": "missing"},
            {"kind": "conditional", "pair": ["X1", "X2"]},
            {"kind": "linear", "pair": ["X1", "X2"]},
        ]
        counters_before = copy.deepcopy(self.session.stats)
        for spec in invalid_specs:
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                self.session.fit_model(spec)
        for key in ("candidate_models", "cv_fits", "final_fits"):
            self.assertEqual(self.session.stats[key], counters_before[key])
        pd.testing.assert_frame_equal(self.frame, after_external_mutation)

    def test_fixed_evidence_enumerates_candidates_but_exposes_only_top_k(self):
        evidence = self.session.fixed_evidence()
        self.assertEqual(
            evidence["candidate_counts"],
            {"null": 1, "linear": 1, "interaction": 6, "conditional": 12},
        )
        self.assertEqual(len(self.session.records), 20)
        self.assertEqual(self.session.stats["candidate_models"], 20)
        self.assertEqual(self.session.stats["cv_fits"], 60)
        self.assertEqual(self.session.stats["final_fits"], 20)
        self.assertEqual(len(evidence["baselines"]), 2)
        visible_ids = set()
        for section in ("baselines", "global_candidates", "conditional_candidates"):
            if section != "baselines":
                self.assertEqual(len(evidence[section]), 3)
                errors = [row["cv_mse"] for row in evidence[section]]
                self.assertEqual(errors, sorted(errors))
            for row in evidence[section]:
                visible_ids.add(row["model_id"])
                self.assertTrue({"model_id", "spec", "cv_mse", "cv_mse_se", "coefficients"} <= row.keys())
        self.assertEqual(self.session.exposed_model_ids, visible_ids)
        self.assertIn(evidence["evidence_id"], self.session.evidence_ids)
        winner = evidence["conditional_candidates"][0]
        self.assertEqual(set(winner["spec"]["pair"]), {"X1", "X2"})
        self.assertEqual(winner["spec"]["gate"], "X3")

    def test_adaptive_diagnosis_finds_gate_without_scanning_every_conditional_model(self):
        baseline = self.session.fit_model({"kind": "linear"})
        pairwise = self.session.diagnose(baseline["model_id"], mode="pairwise")
        self.assertEqual(pairwise["evaluated_candidates"], 6)
        global_winner = pairwise["candidates"][0]
        self.assertEqual(set(global_winner["spec"]["pair"]), {"X1", "X2"})
        stability = self.session.diagnose(
            global_winner["model_id"], mode="stability", term=["X1", "X2"]
        )
        self.assertEqual(stability["evaluated_candidates"], 2)
        self.assertEqual(stability["candidates"][0]["spec"]["gate"], "X3")
        self.assertLess(stability["candidates"][0]["cv_mse"], global_winner["cv_mse"] / 100)
        self.assertEqual(self.session.stats["candidate_models"], 9)
        self.assertEqual(self.session.stats["cv_fits"], 27)
        self.assertEqual(self.session.stats["final_fits"], 9)
        self.assertIn(pairwise["evidence_id"], self.session.evidence_ids)
        self.assertIn(stability["evidence_id"], self.session.evidence_ids)
        with self.assertRaises(ValueError):
            self.session.diagnose("unseen-model", mode="pairwise")

    def test_baseline_ols_helper_preserves_existing_sklearn_fit(self):
        features = self.frame.drop(columns="Y")
        reference = LinearRegression().fit(features, self.frame["Y"])
        actual = fit_ols(features, self.frame["Y"])
        np.testing.assert_array_equal(actual.coef_, reference.coef_)
        self.assertEqual(actual.intercept_, reference.intercept_)
        np.testing.assert_array_equal(actual.predict(features), reference.predict(features))
        self.assertEqual(actual.score(features, self.frame["Y"]), reference.score(features, self.frame["Y"]))


if __name__ == "__main__":
    unittest.main()
