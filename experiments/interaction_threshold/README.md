# Interaction-Strength Benchmark (Stage 1)

This directory contains the first, non-API stage of an interaction-strength benchmark for the live-salmon project.

## Research Question

If we hold the full feature matrix and noise vector fixed, how does changing only the `X4*X5` interaction coefficient affect the generated live-salmon-style datasets?

This stage does **not** run AI scientists yet. It prepares reproducible datasets and sanity checks so later model runs can be compared condition by condition.

## Why These Coefficients?

The benchmark generates four interaction-strength conditions:

- `0.0`: negative control with no interaction contribution in `Y`
- `0.4`: weaker-than-default interaction
- `0.8`: the repository's default interaction strength
- `1.6`: stronger-than-default interaction

These values give one null condition, one sub-default condition, the original condition, and one amplified condition.

## Why `0.0` Is a Negative Control

At `0.0`, the data generating process becomes:

```text
Y = 2*X1 + 0.5*X2 - 1.5*X3 + epsilon
```

So `X4*X5` should contribute nothing to `Y`. That makes `0.0` a clean control for later tests of whether downstream methods claim to detect an interaction when none is present.

## Design Constraints Preserved

This benchmark keeps the original repository defaults fixed for every condition except the interaction coefficient:

- sample size
- number of features
- noise standard deviation
- proxy construction
- random seed structure

All four conditions share the same:

- base feature matrix `X1` to `X20`
- noise vector `epsilon`

So the intended change across conditions is only the interaction coefficient multiplying `X4*X5`.

## Feature Roles Recorded in Metadata

Each condition-specific `ground_truth.json` distinguishes:

- `X1-X3` as direct linear signal variables
- `X4-X5` as interaction participants
- `X6-X15` as noise variables
- `X16-X20` as correlated proxy variables

## How To Reproduce

Run these commands from the repository root.

Generate datasets:

```bash
python experiments/interaction_threshold/generate_datasets.py
```

Run sanity checks:

```bash
python experiments/interaction_threshold/validate_datasets.py
```

If you intentionally want to overwrite generator-managed files under `generated/`, you may add `--force` to the generation command. The default behavior is **no overwrite**.

## Expected Outputs

After generation, the main outputs appear under `experiments/interaction_threshold/generated/`:

- `shared/base_features.csv`
- `shared/base_noise.csv`
- `coef_0p0/live_salmon_data.csv`
- `coef_0p0/ground_truth.json`
- `coef_0p4/live_salmon_data.csv`
- `coef_0p4/ground_truth.json`
- `coef_0p8/live_salmon_data.csv`
- `coef_0p8/ground_truth.json`
- `coef_1p6/live_salmon_data.csv`
- `coef_1p6/ground_truth.json`
- `manifest.json`
- `validation_report.json` after running validation

## What Is Implemented In This Stage

- reproducible dataset generation
- coefficient-specific metadata
- shared-feature/shared-noise construction
- sanity checks for formula consistency and default-condition reproduction
- a no-overwrite default generation policy

## What Is Not Implemented Yet

This first stage does **not** yet:

- run AI scientists
- call OpenRouter or any other model API
- evaluate papers
- update the repository's main evaluation pipeline
- generate benchmark plots or detection curves
