"""Generate reproducible interaction-threshold benchmark datasets."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import (
    DEFAULT_COEFFICIENTS,
    DEFAULT_OUTPUT_ROOT,
    N_FEATURES,
    N_SAMPLES,
    build_ground_truth,
    build_live_dataset,
    coefficient_label,
    generate_base_features_and_noise,
    json_dump,
    managed_output_paths,
    write_csv,
    write_series_csv,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate live-salmon-style datasets across interaction strengths "
            "without touching the repository's default datasets or results."
        )
    )
    parser.add_argument(
        "--coefficients",
        nargs="+",
        type=float,
        default=list(DEFAULT_COEFFICIENTS),
        help="Interaction coefficients to generate.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Output directory for generated artifacts.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite generator-managed files under the output root.",
    )
    return parser.parse_args()


def preflight(output_root: Path, coefficients: list[float], force: bool) -> None:
    existing = [path for path in managed_output_paths(output_root, coefficients) if path.exists()]
    if existing and not force:
        existing_display = "\n".join(f"  - {path.as_posix()}" for path in existing)
        raise FileExistsError(
            "Refusing to overwrite existing outputs. Re-run with --force only if "
            f"you intentionally want to replace generator-managed files:\n{existing_display}"
        )


def main() -> None:
    args = parse_args()
    coefficients = list(args.coefficients)
    output_root = args.output_root

    preflight(output_root, coefficients, args.force)

    features, epsilon = generate_base_features_and_noise()

    write_csv(output_root / "shared" / "base_features.csv", features)
    write_series_csv(output_root / "shared" / "base_noise.csv", epsilon)

    manifest_conditions = []
    for coefficient in coefficients:
        condition_name = coefficient_label(coefficient)
        condition_dir = output_root / condition_name
        dataset = build_live_dataset(features, epsilon, coefficient)

        write_csv(condition_dir / "live_salmon_data.csv", dataset)
        json_dump(condition_dir / "ground_truth.json", build_ground_truth(coefficient))

        manifest_conditions.append(
            {
                "condition_name": condition_name,
                "interaction_coefficient": coefficient,
                "dataset_path": f"{condition_name}/live_salmon_data.csv",
                "ground_truth_path": f"{condition_name}/ground_truth.json",
                "n_rows": N_SAMPLES,
                "n_columns": N_FEATURES + 1,
            }
        )

    manifest = {
        "experiment_name": "interaction_threshold",
        "description": (
            "Reproducible non-API dataset generation for interaction-strength "
            "benchmarking. All conditions share the same X matrix and epsilon "
            "vector; only the X4*X5 coefficient changes."
        ),
        "output_root": output_root.as_posix(),
        "coefficients": coefficients,
        "overwrite_default": False,
        "shared_artifacts": {
            "base_features_path": "shared/base_features.csv",
            "base_noise_path": "shared/base_noise.csv",
        },
        "conditions": manifest_conditions,
    }
    json_dump(output_root / "manifest.json", manifest)

    print("Generated interaction-threshold datasets:")
    for condition in manifest_conditions:
        print(
            f"  - {condition['condition_name']}: "
            f"{condition['dataset_path']} (coef={condition['interaction_coefficient']:.1f})"
        )
    print(f"Manifest: {output_root.as_posix()}/manifest.json")


if __name__ == "__main__":
    main()
