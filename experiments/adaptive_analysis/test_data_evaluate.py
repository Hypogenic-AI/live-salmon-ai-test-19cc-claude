"""Tests for pairing, prompt boundaries, exact scoring, and failed-run accounting."""

from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from experiments.adaptive_analysis.data import CONDITIONS, FEATURE_COLUMNS, make_case, make_summary
from experiments.adaptive_analysis.evaluate import aggregate, score_submission, write_reports


class PairedDataTests(unittest.TestCase):
    def test_shared_covariates_noise_mapping_and_split(self):
        cases = {name: make_case(42, name, 120, 80) for name in CONDITIONS}
        original = cases["global"]
        mapping = original.truth["mapping"]
        pair = [mapping["X4"], mapping["X5"]]
        gate = mapping["X6"]
        for case in cases.values():
            self.assertEqual(case.truth["mapping"], mapping)
            self.assertEqual(case.truth["discovery_rows"], original.truth["discovery_rows"])
            self.assertEqual(case.truth["test_rows"], original.truth["test_rows"])
            self.assertFalse(set(case.truth["discovery_rows"]) & set(case.truth["test_rows"]))
            for split in ("discovery", "test"):
                pd.testing.assert_frame_equal(
                    getattr(case, split).drop(columns="Y"),
                    getattr(original, split).drop(columns="Y"),
                )
        for split in ("discovery", "test"):
            global_frame = getattr(cases["global"], split)
            conditional = getattr(cases["conditional"], split)
            null = getattr(cases["null"], split)
            linear = sum(
                value * global_frame[name]
                for name, value in original.truth["linear_coefficients"].items()
            )
            interaction = 0.8 * global_frame[pair[0]] * global_frame[pair[1]]
            np.testing.assert_allclose(global_frame.Y - linear - interaction, null.Y, atol=1e-14)
            np.testing.assert_allclose(
                conditional.Y - linear
                - np.sqrt(2) * interaction * (conditional[gate] > 0),
                null.Y, atol=1e-14,
            )
        self.assertEqual(cases["global"].truth["feature_roles"][gate], "noise_distractor")
        self.assertEqual(cases["conditional"].truth["feature_roles"][gate], "gate")

    def test_reproducible_and_distinct_cases(self):
        first = make_case(0, "global", 60, 40)
        again = make_case(0, "global", 60, 40)
        other_seed = make_case(1, "global", 60, 40)
        other_condition = make_case(0, "conditional", 60, 40)
        self.assertEqual(first.fingerprint, again.fingerprint)
        pd.testing.assert_frame_equal(first.discovery, again.discovery)
        self.assertNotEqual(first.fingerprint, other_seed.fingerprint)
        self.assertNotEqual(first.fingerprint, other_condition.fingerprint)
        self.assertEqual(list(first.discovery.columns), list(FEATURE_COLUMNS) + ["Y"])

    def test_validation(self):
        for seed in (-1, True, 1.5):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                make_case(seed, "global")
        for args in ((0, "bad", 100, 70), (0, "global", 10, 10), (0, "null", 10, 0)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                make_case(*args)

    def test_summary_uses_only_discovery_and_neutral_label(self):
        case = make_case(15, "conditional", 60, 40)
        summary = make_summary(case.discovery)
        self.assertTrue(summary.startswith("# Dataset: Research Dataset\n"))
        self.assertIn("Number of samples: 40", summary)
        self.assertNotIn("conditional", summary)
        self.assertNotIn("gate_direction", summary)
        case.test.loc[:, "Y"] = 987654321.0
        self.assertEqual(summary, make_summary(case.discovery))
        self.assertNotIn("987654321", summary)


class ScoringTests(unittest.TestCase):
    def test_global_requires_right_pair_and_positive_direction(self):
        case = make_case(3, "global", 60, 40)
        spec = case.truth["spec"]
        name = "*".join(spec["pair"])
        record = {"spec": spec, "coefficients": {name: 0.8}}
        scores = score_submission(case, record, case.test.Y.to_numpy())
        self.assertTrue(scores["mechanism_correct"])
        self.assertEqual(scores["test_mse"], 0.0)
        self.assertIsNone(scores["gate_correct"])
        self.assertIsNone(scores["false_signal"])
        record["coefficients"][name] = -0.8
        self.assertFalse(score_submission(case, record, case.test.Y.to_numpy())["mechanism_correct"])

    def test_conditional_direction_is_not_just_right_feature_names(self):
        case = make_case(3, "conditional", 60, 40)
        record = {"spec": case.truth["spec"], "group_slopes": {"nonpositive": 0.03, "positive": 1.12}}
        scores = score_submission(case, record, np.zeros(len(case.test)))
        self.assertTrue(scores["mechanism_correct"])
        record["group_slopes"] = {"nonpositive": 1.12, "positive": 0.03}
        scores = score_submission(case, record, np.zeros(len(case.test)))
        self.assertTrue(scores["gate_correct"])
        self.assertFalse(scores["active_direction_correct"])
        self.assertFalse(scores["mechanism_correct"])

    def test_null_and_false_structure(self):
        case = make_case(4, "null", 60, 40)
        scores = score_submission(case, {"spec": {"kind": "null"}}, np.zeros(len(case.test)))
        self.assertTrue(scores["mechanism_correct"])
        self.assertFalse(scores["false_signal"])
        self.assertIsNone(scores["pair_correct"])
        record = {"spec": {"kind": "conditional", "pair": ["X1", "X2"], "gate": "X3"}}
        scores = score_submission(case, record, np.zeros(len(case.test)))
        self.assertTrue(scores["false_signal"])
        self.assertTrue(scores["false_condition"])
        self.assertFalse(scores["mechanism_correct"])

    def test_missing_or_invalid_predictions_cannot_succeed(self):
        case = make_case(3, "null", 60, 40)
        for predictions in (None, [0.0], np.full(20, np.nan), np.zeros((20, 1))):
            with self.subTest(predictions=repr(predictions)), self.assertRaises(ValueError):
                score_submission(case, {"spec": {"kind": "null"}}, predictions)


class ReportingTests(unittest.TestCase):
    def test_retry_keeps_failed_attempt_in_completion_and_cost_denominators(self):
        rows = [{"seed": 0, "condition": "null", "workflow": "adaptive",
                 "status": "success", "test_mse": 1.0, "mechanism_correct": True,
                 "attempt_count": 2, "failed_attempt_count": 1,
                 "incomplete_attempt_count": 0, "reported_cost": 0.02}]
        group = aggregate(rows)["groups"][0]
        self.assertEqual(group["n_total"], 1)
        self.assertEqual(group["n_attempts"], 2)
        self.assertEqual(group["n_failed_attempts"], 1)
        self.assertEqual(group["mechanism_success_per_episode"], 1.0)
        self.assertEqual(group["mechanism_success_per_attempt"], 0.5)
        self.assertEqual(group["metrics"]["reported_cost"]["sum"], 0.02)

    def test_failures_and_complete_pair_denominators(self):
        rows = [
            {"seed": 0, "condition": "null", "workflow": "A", "status": "success", "test_mse": 1.0, "mechanism_correct": True, "false_signal": False, "fit_count": 10},
            {"seed": 1, "condition": "null", "workflow": "A", "status": "failed", "test_mse": 0.0, "mechanism_correct": True, "fit_count": 4},
            {"seed": 0, "condition": "null", "workflow": "B", "status": "success", "test_mse": 2.0, "mechanism_correct": False, "false_signal": True, "fit_count": 2},
            {"seed": 1, "condition": "null", "workflow": "B", "status": "success", "test_mse": 1.0, "mechanism_correct": True, "false_signal": False, "fit_count": 2},
        ]
        report = aggregate(rows)
        group = report["groups"][0]
        self.assertEqual((group["n_total"], group["n_succeeded"], group["n_failed"]), (2, 1, 1))
        self.assertEqual(group["metrics"]["test_mse"], {"mean": 1.0, "n_observed": 1, "sum": 1.0})
        self.assertEqual(group["metrics"]["fit_count"]["mean"], 7.0)
        self.assertEqual(group["mechanism_success_per_attempt"], 0.5)
        paired = next(row for row in report["paired_differences"] if row["metric"] == "test_mse")
        self.assertEqual(paired["mean_difference"], -1.0)
        self.assertEqual((paired["n_pairs"], paired["n_shared_seeds"]), (1, 2))
        with tempfile.TemporaryDirectory() as directory:
            write_reports(rows, directory)
            for name in ("aggregate.json", "groups.csv", "paired.csv", "report.md"):
                self.assertTrue((Path(directory) / name).exists())

    def test_duplicate_rows_rejected(self):
        row = {"seed": 0, "condition": "null", "workflow": "A", "status": "failed"}
        with self.assertRaises(ValueError):
            aggregate([row, row])


if __name__ == "__main__":
    unittest.main()
