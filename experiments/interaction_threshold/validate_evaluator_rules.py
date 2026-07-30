"""Small no-API regression tests for the rule-based interaction evaluator."""

from __future__ import annotations

import sys

from evaluate_outputs import evaluate_content


TEST_CASES = [
    {
        "name": "tested_interactions_but_no_evidence_is_not_detection",
        "coefficient": 0.8,
        "response": (
            "We tested interactions among the top predictors but found no evidence "
            "for significant interaction effects. The final model remained linear."
        ),
        "expected": {
            "detected_true_interaction": False,
            "detected_wrong_interaction": False,
            "false_positive_interaction": False,
            "mentions_interaction": True,
            "conclusion_says_no_interaction": True,
        },
    },
    {
        "name": "no_significant_interaction_is_not_detection",
        "coefficient": 0.8,
        "response": (
            "No significant interaction terms were detected, and there was no "
            "evidence for nonlinear effects."
        ),
        "expected": {
            "detected_true_interaction": False,
            "detected_wrong_interaction": False,
            "false_positive_interaction": False,
            "mentions_interaction": True,
            "conclusion_says_no_interaction": True,
        },
    },
    {
        "name": "x4_x5_significant_counts_as_true_detection",
        "coefficient": 0.8,
        "response": (
            "The final model shows that X4 and X5 interact significantly in "
            "predicting Y, indicating an important X4*X5 interaction effect."
        ),
        "expected": {
            "detected_true_interaction": True,
            "detected_wrong_interaction": False,
            "false_positive_interaction": False,
            "mentions_interaction": True,
            "conclusion_says_no_interaction": False,
        },
    },
    {
        "name": "x1_x2_significant_counts_as_wrong_detection",
        "coefficient": 0.8,
        "response": (
            "We found a significant interaction between X1 and X2, and this "
            "interaction term was retained in the final predictive model."
        ),
        "expected": {
            "detected_true_interaction": False,
            "detected_wrong_interaction": True,
            "false_positive_interaction": False,
            "mentions_interaction": True,
            "conclusion_says_no_interaction": False,
        },
    },
    {
        "name": "coef_zero_positive_x4_x5_claim_is_false_positive",
        "coefficient": 0.0,
        "response": (
            "A significant X4*X5 interaction was detected and appears to be an "
            "important predictor of Y."
        ),
        "expected": {
            "detected_true_interaction": True,
            "detected_wrong_interaction": False,
            "false_positive_interaction": True,
            "mentions_interaction": True,
            "conclusion_says_no_interaction": False,
        },
    },
]


def main() -> None:
    failures = []

    for case in TEST_CASES:
        observed = evaluate_content(case["response"], case["coefficient"])
        case_failures = []
        for key, expected_value in case["expected"].items():
            observed_value = observed[key]
            if observed_value != expected_value:
                case_failures.append(
                    f"{key}: expected {expected_value!r}, observed {observed_value!r}"
                )

        if case_failures:
            failures.append((case["name"], case_failures, observed))
            print(f"[FAIL] {case['name']}")
            for item in case_failures:
                print(f"  - {item}")
            print(f"  observed notes: {observed['notes']}")
        else:
            print(f"[PASS] {case['name']}")

    print(f"Checked {len(TEST_CASES)} evaluator rule cases.")
    if failures:
        print(f"Failures: {len(failures)}")
        raise SystemExit(1)

    print("All evaluator rule regression checks passed.")


if __name__ == "__main__":
    main()
