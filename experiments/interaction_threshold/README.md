# Interaction-Strength Benchmark (Stages 1-2)

This directory contains the first non-API stages of an interaction-strength benchmark for the live-salmon project.

## Research Question

If we hold the full feature matrix and noise vector fixed, how does changing only the `X4*X5` interaction coefficient affect the generated live-salmon-style datasets?

These stages do **not** run AI scientists yet. They prepare reproducible datasets, sanity checks, and a dry-run planning layer so later model runs can be compared condition by condition.

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

Plan dry-run model calls for one model across selected coefficients:

```bash
python experiments/interaction_threshold/dry_run_runner.py \
  --model-id openai/gpt-4.1 \
  --coefficients 0.0 0.8 1.6 \
  --runs 2
```

The dry-run runner:

- reuses the existing project summary style from `src/prepare_data_summary.py`
- mirrors the main project prompt style
- writes cacheable dry-run records under `experiments/interaction_threshold/planned_calls/`
- does not read or print API keys
- does not make any external API calls

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

After running the dry-run runner, planned call records appear under:

- `planned_calls/coef_0p0/<model_slug>/run_01__<prompt_hash>.json`
- `planned_calls/coef_0p8/<model_slug>/run_02__<prompt_hash>.json`

## What Is Implemented In These Stages

- reproducible dataset generation
- coefficient-specific metadata
- shared-feature/shared-noise construction
- sanity checks for formula consistency and default-condition reproduction
- a no-overwrite default generation policy
- dry-run planning for one model across one or more coefficients
- prompt hashing and cacheable dry-run records

## What Is Not Implemented Yet

These stages do **not** yet:

- run AI scientists
- call OpenRouter or any other model API
- execute planned model calls
- evaluate papers
- update the repository's main evaluation pipeline
- generate benchmark plots or detection curves
