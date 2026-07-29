"""Run sanity checks for the interaction-threshold benchmark datasets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from common import (
    ALLCLOSE_ATOL,
    ALLCLOSE_RTOL,
    DEFAULT_COEFFICIENTS,
    DEFAULT_OUTPUT_ROOT,
    FEATURE_ROLE_GROUPS,
    LINEAR_COEFFICIENTS,
    PROXY_SPECS,
    coefficient_label,
    expected_dataset_columns,
    expected_feature_columns,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate generated datasets for the interaction-threshold benchmark."
    )
    parser.add_argument(
        "--input-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Directory containing generated datasets and metadata.",
    )
    parser.add_argument(
        "--reference-sample",
        type=Path,
        default=Path("datasets/live_salmon_sample.csv"),
        help="Reference sample for checking the 0.8 condition against the default setup.",
    )
    parser.add_argument(
        "--reference-ground-truth",
        type=Path,
        default=Path("datasets/ground_truth.json"),
        help="Reference metadata for checking the 0.8 condition against the default setup.",
    )
    return parser.parse_args()


def record_check(results: list[dict], name: str, passed: bool, details: str) -> None:
    results.append({"name": name, "passed": passed, "details": details})


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    args = parse_args()
    input_root = args.input_root
    manifest = load_json(input_root / "manifest.json")
    base_features = pd.read_csv(input_root / "shared" / "base_features.csv")
    epsilon = pd.read_csv(input_root / "shared" / "base_noise.csv")["epsilon"]

    checks: list[dict] = []
    expected_coefficients = np.array(DEFAULT_COEFFICIENTS, dtype=float)
    manifest_coefficients = np.array(manifest.get("coefficients", []), dtype=float)
    record_check(
        checks,
        "manifest_coefficients_match_expected",
        manifest_coefficients.shape == expected_coefficients.shape
        and np.allclose(
            manifest_coefficients,
            expected_coefficients,
            atol=ALLCLOSE_ATOL,
            rtol=ALLCLOSE_RTOL,
        ),
        f"Manifest coefficients: {manifest.get('coefficients', [])}",
    )

    expected_columns = expected_dataset_columns()
    feature_columns = expected_feature_columns()
    datasets: dict[float, pd.DataFrame] = {}
    metadata_by_coefficient: dict[float, dict] = {}

    for condition in manifest["conditions"]:
        coefficient = float(condition["interaction_coefficient"])
        condition_dir = input_root / coefficient_label(coefficient)
        dataset = pd.read_csv(condition_dir / "live_salmon_data.csv")
        metadata = load_json(condition_dir / "ground_truth.json")
        datasets[coefficient] = dataset
        metadata_by_coefficient[coefficient] = metadata

        shape_ok = dataset.shape == (1000, 21)
        columns_ok = dataset.columns.tolist() == expected_columns
        record_check(
            checks,
            f"{condition['condition_name']}_shape_and_columns",
            shape_ok and columns_ok,
            f"shape={dataset.shape}, columns={dataset.columns.tolist()}",
        )

        features_match = np.allclose(
            dataset[feature_columns].to_numpy(),
            base_features.to_numpy(),
            atol=ALLCLOSE_ATOL,
            rtol=ALLCLOSE_RTOL,
        )
        record_check(
            checks,
            f"{condition['condition_name']}_shares_base_features",
            features_match,
            "Feature matrix matches shared/base_features.csv",
        )

        metadata_coefficient_ok = np.allclose(
            [metadata["interaction_coefficient"]],
            [coefficient],
            atol=ALLCLOSE_ATOL,
            rtol=ALLCLOSE_RTOL,
        )
        role_groups = metadata["feature_roles"]
        roles_ok = (
            role_groups["direct_linear_signal_variables"] == FEATURE_ROLE_GROUPS["direct_linear_signal_variables"]
            and role_groups["interaction_participants"] == FEATURE_ROLE_GROUPS["interaction_participants"]
            and role_groups["noise_variables"] == FEATURE_ROLE_GROUPS["noise_variables"]
            and role_groups["correlated_proxy_variables"] == FEATURE_ROLE_GROUPS["correlated_proxy_variables"]
        )
        record_check(
            checks,
            f"{condition['condition_name']}_metadata_roles_and_coefficient",
            metadata_coefficient_ok and roles_ok,
            (
                f"interaction_coefficient={metadata['interaction_coefficient']}, "
                "feature role groups checked"
            ),
        )

    linear_part = (
        LINEAR_COEFFICIENTS["X1"] * base_features["X1"]
        + LINEAR_COEFFICIENTS["X2"] * base_features["X2"]
        + LINEAR_COEFFICIENTS["X3"] * base_features["X3"]
    )
    interaction_term = base_features["X4"] * base_features["X5"]

    y_zero = datasets[0.0]["Y"]
    expected_y_zero = linear_part + epsilon
    record_check(
        checks,
        "coef_0p0_removes_interaction_effect",
        np.allclose(y_zero, expected_y_zero, atol=ALLCLOSE_ATOL, rtol=ALLCLOSE_RTOL),
        "Y for coef=0.0 matches linear part plus shared epsilon",
    )

    y_default = datasets[0.8]["Y"]
    expected_y_default = linear_part + 0.8 * interaction_term + epsilon
    record_check(
        checks,
        "coef_0p8_matches_default_formula",
        np.allclose(y_default, expected_y_default, atol=ALLCLOSE_ATOL, rtol=ALLCLOSE_RTOL),
        "Y for coef=0.8 matches the repository's default formula",
    )

    only_interaction_changes = True
    for coefficient, dataset in datasets.items():
        delta = dataset["Y"] - y_zero
        expected_delta = coefficient * interaction_term
        if not np.allclose(delta, expected_delta, atol=ALLCLOSE_ATOL, rtol=ALLCLOSE_RTOL):
            only_interaction_changes = False
            break
    record_check(
        checks,
        "only_interaction_term_changes_across_conditions",
        only_interaction_changes,
        "Each condition differs from coef=0.0 only through coefficient * (X4*X5)",
    )

    proxy_alignment_ok = True
    proxy_details = []
    direct_and_interaction = ["X1", "X2", "X3", "X4", "X5"]
    correlation_matrix = base_features[direct_and_interaction + FEATURE_ROLE_GROUPS["correlated_proxy_variables"]].corr()
    for proxy, (source, _, _) in PROXY_SPECS.items():
        source_corr = correlation_matrix.loc[proxy, source]
        strongest_source = max(
            direct_and_interaction,
            key=lambda candidate: abs(correlation_matrix.loc[proxy, candidate]),
        )
        proxy_details.append(f"{proxy}->{source}: corr={source_corr:.3f}, strongest={strongest_source}")
        if abs(source_corr) < 0.65 or strongest_source != source:
            proxy_alignment_ok = False
    record_check(
        checks,
        "proxy_variables_remain_correlated_with_intended_sources",
        proxy_alignment_ok,
        "; ".join(proxy_details),
    )

    if args.reference_sample.exists():
        reference_sample = pd.read_csv(args.reference_sample)
        default_sample = datasets[0.8].head(len(reference_sample))
        sample_matches = (
            reference_sample.columns.tolist() == default_sample.columns.tolist()
            and np.allclose(
                reference_sample.to_numpy(),
                default_sample.to_numpy(),
                atol=ALLCLOSE_ATOL,
                rtol=ALLCLOSE_RTOL,
            )
        )
        record_check(
            checks,
            "coef_0p8_matches_reference_sample",
            sample_matches,
            f"Compared first {len(reference_sample)} rows against {args.reference_sample.as_posix()}",
        )

    if args.reference_ground_truth.exists():
        reference_ground_truth = load_json(args.reference_ground_truth)
        default_metadata = metadata_by_coefficient[0.8]
        metadata_matches = (
            default_metadata["linear_coefficients"] == reference_ground_truth["linear_coefficients"]
            and np.allclose(
                [default_metadata["interaction_coefficient"]],
                [reference_ground_truth["interaction_term"]["coefficient"]],
                atol=ALLCLOSE_ATOL,
                rtol=ALLCLOSE_RTOL,
            )
        )
        record_check(
            checks,
            "coef_0p8_metadata_matches_reference_ground_truth",
            metadata_matches,
            f"Compared against {args.reference_ground_truth.as_posix()}",
        )

    all_passed = all(check["passed"] for check in checks)
    report = {
        "experiment_name": "interaction_threshold",
        "input_root": input_root.as_posix(),
        "all_passed": all_passed,
        "n_checks": len(checks),
        "checks": checks,
    }

    report_path = input_root / "validation_report.json"
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    for check in checks:
        status = "PASS" if check["passed"] else "FAIL"
        print(f"[{status}] {check['name']}: {check['details']}")
    print(f"Validation report: {report_path.as_posix()}")
    if not all_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
