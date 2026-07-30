# Interaction-Strength Benchmark

This directory contains a self-contained interaction-strength benchmark extension for the live-salmon project. It includes reproducible dataset generation, validation checks, a dry-run-first model runner, opt-in API execution, and a lightweight rule-based evaluator.

## Research Question

If we hold the feature matrix, noise vector, prompt format, and data-summary style fixed, does increasing the `X4×X5` interaction coefficient make AI scientists more likely to explicitly detect the true interaction?

The dataset-generation layer isolates the interaction coefficient as the only intended change across conditions.

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
- `X4 and X5` as interaction participants
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
  --coefficients 0.0 0.4 0.8 1.6 \
  --runs 3
```

The dry-run runner:

- reuses the existing project summary style from `src/prepare_data_summary.py`
- mirrors the main project prompt style
- writes cacheable dry-run records under `experiments/interaction_threshold/planned_calls/`
- does not read or print API keys
- does not make any external API calls

Run actual execution only when you explicitly want API calls:

```bash
export OPENROUTER_KEY=...
python experiments/interaction_threshold/dry_run_runner.py \
  --model-id openai/gpt-4.1 \
  --coefficients 0.0 0.4 0.8 1.6 \
  --runs 3 \
  --execute
```

Required environment variable for `--execute`:

- `OPENROUTER_KEY`

Smoke-test example:

```bash
export OPENROUTER_KEY=...
python experiments/interaction_threshold/dry_run_runner.py \
  --execute \
  --model-id openai/gpt-4.1 \
  --coefficients 0.8 \
  --runs 1
```

Warning: `--execute` may cost money because it makes real API calls.

Run the lightweight evaluator on saved model outputs:

```bash
python experiments/interaction_threshold/evaluate_outputs.py
```

Run the small no-API evaluator rule regression checks:

```bash
python experiments/interaction_threshold/validate_evaluator_rules.py
```

The evaluator:

- reads model outputs from `experiments/interaction_threshold/outputs/`
- writes summary CSVs to `experiments/interaction_threshold/evaluations/`
- uses lightweight rule-based text matching only
- does not call any external API
- is not a definitive human or LLM judgment

## Preliminary Result

In a small local GPT-4.1 sweep with 4 coefficients × 3 runs, the rule-based evaluator found 0/12 explicit detections of the true X4×X5 interaction. All runs mentioned interaction or nonlinearity, but each concluded that there was no meaningful interaction. This result is preliminary because it uses one model and a lightweight rule-based evaluator.

If you intentionally want to overwrite generator-managed files under `generated/`, you may add `--force` to the generation command. The default behavior is **no overwrite**.

Generated datasets, planned calls, model outputs, and evaluation CSVs are ignored by git and can be regenerated locally.

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

After running with `--execute`, real model outputs appear under:

- `outputs/coef_0p8/<model_slug>/run_01__<prompt_hash>.json`

After running the evaluator, summaries appear under:

- `evaluations/per_run_summary.csv`
- `evaluations/aggregate_by_coefficient.csv`

## What Is Implemented In These Stages

- reproducible dataset generation
- coefficient-specific metadata
- shared-feature/shared-noise construction
- sanity checks for formula consistency and default-condition reproduction
- a no-overwrite default generation policy
- dry-run planning for one model across one or more coefficients
- prompt hashing and cacheable dry-run records
- opt-in execution via `--execute`
- cached real outputs under `outputs/`
- lightweight rule-based evaluation summaries under `evaluations/`

## What Is Not Implemented Yet

These stages do **not** yet:

- provide definitive human or LLM-based judgment of interaction detection
- update the repository's main evaluation pipeline
- generate benchmark plots or detection curves
