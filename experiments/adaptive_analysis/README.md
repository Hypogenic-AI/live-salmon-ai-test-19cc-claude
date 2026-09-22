# Fixed evidence versus adaptive analysis

This experiment compares **a fixed statistical workflow followed by one LLM
response** with **the same LLM choosing statistical analyses after seeing their
results**. Both workflows use the same fitted models, numerical tools, discovery
data, and held-out evaluator. See [REPORT.md](REPORT.md) for what has actually run.

## Why add a conditional interaction?

The original Live Salmon task contains an interaction with the same coefficient
across all samples. Finding that interaction answers the main nonlinear question,
but offers limited evidence about whether an analyst checks where a relationship
holds. We add one variant in which the existing interaction is active only when
another observed feature is positive:

```text
Original:    Y = 2 X1 + 0.5 X2 - 1.5 X3 + 0.8 X4 X5 + noise
Conditional: Y = 2 X1 + 0.5 X2 - 1.5 X3
                + sqrt(2) * 0.8 X4 X5 * I(X6 > 0) + noise
Null:        Y = noise
```

The feature distribution, correlated proxies, 20 columns, 1,000 samples, and
standard-normal noise remain those of the original generator. X6 changes role
from distractor to conditioning variable. Because the gate is independent and
active with probability one half, multiplying by `sqrt(2)` preserves interaction
signal variance (`0.64`). It does not preserve every aspect of difficulty.

The conditional variant still has a detectable pooled interaction: its population
coefficient is about `0.566`. The full relationship additionally requires finding
that its coefficient is zero for `X6 <= 0` and about `1.131` for `X6 > 0`.
These are **properties of the generator, not experimental results**. A scan of
190 pairs remains useful; the added question is whether that average effect
describes all samples. Stability tools inspect interaction slopes, since residual
means or variances alone need not reveal the gate.

Fixed analysis can solve this task too. Both workflows can check conditional
interactions. The experiment tests analysis choices, use of evidence, and total
cost without assuming that an agent will help. Keeping the original and null
conditions also checks whether a workflow adds unnecessary explanations.

## What is reused?

| Base component | Use in this experiment |
| --- | --- |
| `datasets/generate_live_salmon_data.py` | Import feature, live-target, and null-target generators; wrap paired seeds, relabeling, and the one conditional target. |
| `src/prepare_data_summary.py` | Use the original summary on discovery rows only, with a neutral label. |
| `src/run_ai_scientists.py` | Reuse `call_openrouter`, including its temperature `0.7` and output cap `4096`. Supply workflow-specific prompts. |
| `src/baseline_analysis.py` | Extract its unchanged `LinearRegression().fit` operation into `fit_ols`; both the old script and the new tools call it. |
| Known-ground-truth evaluation | Score submitted model objects deterministically. No extra LLM paper-extraction call is needed. |

The original summary-to-paper workflow is **not** workflow A below. A is an
expanded baseline with actual model fitting and conditional evidence. The base
OLS/Lasso/random-forest script was separate from the original model input; its
hardcoded `X4 * X5` check is not used as a discovery tool. Lasso and random forest
remain in the original script rather than enlarging the new action menu.

This directory adds data wrapping, shared analysis tools, two runner modes, and
structured evaluation. No agent framework, execution sandbox, Jev integration,
or dependency on an unmerged PR is required.

## Workflows and tools

**A — fixed:** compute the intercept-only and linear models, all 190 global
interactions, and all `190 * 18 = 3,420` conditional interactions. Then the LLM
chooses one fitted model in one response. Evidence includes the two baselines
and the top 10 candidates of each interaction family, ranked by discovery CV MSE.
All candidate records are saved, but are not all placed in the prompt.

**B — adaptive:** start with the same discovery summary. The LLM chooses up to
eight analysis actions and may submit earlier. After the limit it can only submit.
The tools use the same models and evidence fields as A:

| Tool | Arguments and result |
| --- | --- |
| `fit_model` | A `spec` with `kind`: `null`, `linear`, `interaction`, or `conditional`; the latter kinds require a two-feature `pair`, and conditional also requires `gate`. Returns a fitted model and CV scores. |
| `diagnose` | An exposed `model_id` and `mode`: `pairwise` scans all pairs; `stability` additionally takes a `term` pair and scans the remaining conditioning variables. Returns top-ranked candidates. |
| `submit` | An exposed `model_id`, supporting `evidence_ids`, and a short `explanation`. Freezes the selection. |

For example, an adaptive trajectory can fit the linear model, scan all pairs,
check stability for the best-looking pair, and submit a conditional model. The
runner does not prescribe that trajectory. It may miss a needed check or pursue
an unhelpful candidate.

All non-null models include the 20 main effects. Conditional models contain both
the global product and its gated product; neither group's coefficient is forced
to zero. The only allowed threshold is zero. Both workflows know the candidate
family, not which condition or variable roles generated the current dataset.
This is a bounded analysis task, not unrestricted scientific discovery.

The candidate table and its scores are exploratory evidence, not
multiplicity-corrected significance tests. The tools perform statistical search;
the LLM arranges or interprets that search. Success is not evidence that an LLM
invented a better statistical estimator.

## Data isolation and measurement

* A seed pairs features, Gaussian noise, anonymous column roles, and the row split
  across all three conditions. Relabeling preserves the original proxy structure.
  Newly generated episodes are not claimed to reproduce historical CSVs exactly.
* Each episode has 700 discovery and 300 held-out rows. Five shuffled, seed-fixed
  CV folds use discovery data only. A and B share the folds.
* Tools receive only discovery data. Condition names, original variable roles,
  mappings, truth, and held-out values are not included in requests. Prediction
  and scoring happen after submission; no test feedback is returned to the LLM.
* A and B have separate session caches. Within a session, repeated models reuse
  fits. Every candidate's CV fits and final fit count, including undisplayed
  candidates; a batch tool request is not one fit.
* Compare held-out MSE, exact interaction/condition recovery, false conditional
  selections on the global task, false signal selections on null data, completion
  rates, tokens, and elapsed time. Keep failed attempts and report denominators.
* Conditional direction recovery is a descriptive check: the fitted positive-side
  slope must be positive and exceed the absolute nonpositive-side slope. This is
  not a hypothesis test or a claim that a coefficient is exactly zero.
* Provider cost is reported only when supplied. Tokens are not automatically
  converted into an unverified dollar estimate. Cached runs are identified as such.

The planned pilot is 10 seeds (`101` through `110`), three conditions, and two
workflows: 30 fixed LLM responses and 30 adaptive trajectories. Development seeds
are separate (`9001` through `9003`). This small experiment compares complete
workflows; information volume, model call count, and feedback differ. It does not
isolate the causal contribution of feedback alone or establish a calibrated
false-positive rate.

## Run from the repository root

Use the existing dependency lock, without changing project dependencies:

```bash
uv sync --frozen --no-install-project
.venv/bin/python -m unittest discover -s experiments/adaptive_analysis -p 'test_*.py' -v

# Print the plan only: no API call and no full candidate search.
.venv/bin/python -m experiments.adaptive_analysis.run

# Exercise real statistics/evaluation without a model: an OFFLINE REFERENCE.
.venv/bin/python -m experiments.adaptive_analysis.run --offline --seeds 9001

# Render the resulting offline-reference tables.
.venv/bin/python -m experiments.adaptive_analysis.evaluate \
  experiments/adaptive_analysis/artifacts/offline_summary.json \
  --output-dir experiments/adaptive_analysis/artifacts/offline-report
```

Configure `OPENROUTER_KEY` in the local environment before real model calls. Do
not commit credentials. Offline reference results must not be labeled as A/B LLM
results. The default requested model is `openai/gpt-4.1`. The inherited transport
does not expose the provider-resolved model/version, so logs explicitly keep
`actual_model` unknown; requested identity and frozen configuration are recorded.

```bash
# Development run; includes actual billable API calls.
.venv/bin/python -m experiments.adaptive_analysis.run --execute --seeds 9002

# Planned pilot, after freezing implementation and prompts.
.venv/bin/python -m experiments.adaptive_analysis.run --execute \
  --seeds 101 102 103 104 105 106 107 108 109 110

.venv/bin/python -m experiments.adaptive_analysis.evaluate \
  experiments/adaptive_analysis/artifacts/summary.json \
  --output-dir experiments/adaptive_analysis/artifacts/pilot-report
```

Artifacts are written beneath this directory's ignored `artifacts/` folder by
default. Run metadata includes configuration/code/data identity, actual usage,
actions, evidence, submitted model, and evaluation. Successful matching episodes
can be resumed; failed attempts need explicit `--retry-failed` and are preserved.

## Roadmap and related work

This implements one concrete task under [roadmap #1](https://github.com/Hypogenic-AI/live-salmon-ai-test-19cc-claude/issues/1),
which asks for task design and evaluation of current AI agents. The roadmap does
not prescribe this particular conditional mechanism.

[PR #4](https://github.com/Hypogenic-AI/live-salmon-ai-test-19cc-claude/pull/4)
already examines time-dependent coefficient changes. Here the condition is a
feature of a static multivariate sample, and the comparison concerns executed
analysis workflows. [PR #5](https://github.com/Hypogenic-AI/live-salmon-ai-test-19cc-claude/pull/5)
compares precomputed information conditions. This experiment contrasts fixed
precomputation with feedback-dependent use of a shared toolset.
