# Can an AI analyst decide which statistical check to run next?

This experiment asks whether an AI analyst can investigate a relationship beyond
its first promising result, and what that ability costs. It compares **fixed
statistical analysis followed by one AI decision** with **an agent choosing
statistical analyses from intermediate results**. Both use the same candidate
model family, OLS implementation, cross-validation folds, and scoring rule.

This contributes a task and an executed evaluation to
[roadmap #1](https://github.com/Hypogenic-AI/live-salmon-ai-test-19cc-claude/issues/1),
which asks contributors to design a task and explore how current AI agents perform.
The conditional-interaction task is this PR's proposed implementation of that item.

**The main experiment is complete:** 180 formal episodes across three model
configurations and two prompts, plus 36 separate development episodes. With
Astra and the basic prompt, both workflows selected the correct structure in
15/15 cases. The agent used 94.3% fewer statistical fits, but about 3.10 times the
API cost. Other configurations exposed missed follow-up analyses, incorrect
numerical comparisons, and invalid tool actions. See [the report](REPORT.md)
and [the reproducible evidence](results/model_prompt/README.md).

## The problem this task makes observable

The original Live Salmon generator has 20 variables, linear effects, correlated
proxies, and one interaction whose coefficient is constant across samples. A
fixed scan of all 190 variable pairs can find that interaction. Asking an agent
to perform that scan alone provides little evidence about its ability to decide
what to investigate next.

We change one term: the interaction is active only when another observed variable
is positive. A pooled pairwise scan still finds a useful interaction, but misses
where it applies. An analyst can then ask whether its strength changes across
conditions. An exhaustive statistical workflow can also answer that question;
the experiment measures whether an agent chooses the relevant checks, interprets
their results correctly, and uses fewer resources.

For example, an interaction between X4 and X5 might help predict Y overall, while
actually operating only in samples with X6 > 0. Stopping after the pairwise scan
misses that condition. Conversely, adding a condition to a genuinely constant
interaction adds unnecessary structure. Pure-noise data tests whether the analyst
will select the null model at all.

## One small change to the data-generating process

```text
Global:      Y = 2 X1 + 0.5 X2 - 1.5 X3 + 0.8 X4 X5 + noise
Conditional: Y = 2 X1 + 0.5 X2 - 1.5 X3
                + sqrt(2) * 0.8 X4 X5 * I(X6 > 0) + noise
Null:        Y = noise
```

The original feature distribution, proxies, 20 variables, 1,000 observations,
and standard-normal noise are retained. X6 takes the role of a conditioning
variable in the new task. The independent gate is active with probability one
half, so the `sqrt(2)` scaling preserves interaction signal variance (0.64).
It does not make the two tasks identical in difficulty.

The pooled interaction coefficient in the conditional population is about 0.566;
its two group coefficients are 0 and about 1.131. These are generator properties,
not estimates supplied to the AI. Feature roles are anonymously relabeled per
seed. The model receives neither the condition label nor the true pair/gate.

## What A and B actually do

| | A: fixed evidence + AI | B: adaptive agent |
|---|---|---|
| Starting information | Discovery summary plus precomputed evidence | The same discovery summary |
| Statistical work | Fit null and linear baselines, all 190 interactions, and all 3,420 pair/gate combinations | Choose analyses after seeing their results; at most eight analysis actions |
| Evidence shown | Both baselines and the top ten candidates from each interaction family | Results of requested analyses, with the same candidate-card fields and ranking |
| AI decision | One response selects an exposed model | Each response requests one action or submits an exposed model |
| Evaluation | Freeze the selection, then score on hidden data | The same evaluator, used only after submission |

**A is a new comparison workflow in this PR.** The repository's original pipeline
sends summary statistics to an LLM and asks for a paper; its separate statistical
baseline script was not an interactive analysis environment. A adds model fitting
and conditional evidence so that B is compared with a capable fixed workflow.

The agent has three tools:

| Tool | Numerical work performed by Python |
|---|---|
| `fit_model(spec)` | Fit a null, linear, interaction, or conditional candidate; return coefficients and five-fold discovery CV MSE. |
| `diagnose(..., mode="pairwise")` | Fit all 190 pairwise interaction candidates; return the ten lowest-CV candidates. |
| `diagnose(..., mode="stability", term=pair)` | For one chosen pair, fit all 18 other features as gates; return the top ten candidates and group slopes. |
| `submit(model_id, evidence_ids, explanation)` | Select an already exposed candidate and end the analysis. |

`diagnose` has two modes, so the table lists four actions but only three tools.
A possible path is `linear → pairwise → stability for a promising pair → submit`.
The runner does not prescribe that path. Each scan consumes one action but can
fit many models; all underlying fits are counted. Repeated fits are cached.

Every non-null candidate retains all 20 main effects. A conditional candidate
adds both the pair product and its gated product, allowing both groups to have
nonzero interaction slopes. The only supported gate threshold is zero. This is
a bounded task about selecting and interpreting analyses; the agent does not
invent estimators or execute arbitrary code.

## Reuse and implementation scope

| Existing component | Reuse or change |
|---|---|
| `datasets/generate_live_salmon_data.py` | Reuse features and global/null targets; add a wrapper for the conditional target, paired splits, and anonymous roles. |
| `src/prepare_data_summary.py` | Reuse the summary formatter on discovery rows only. |
| `src/baseline_analysis.py` | Extract the existing `LinearRegression().fit` operation into `fit_ols`, shared by the original script and new tools. |
| `src/run_ai_scientists.py` | Reuse OpenRouter transport; add optional generation parameters and response/usage metadata while preserving legacy defaults. |
| New experiment directory | Add shared analysis tools, fixed/adaptive runners, structured selection, and deterministic hidden-data scoring. |

The original Lasso/random-forest baseline remains separate. Its hardcoded true
interaction is not used as a discovery shortcut. No agent framework or new
project dependency is introduced.

## Model and prompt comparison

The completed follow-up crosses:

- GPT-4.1 (temperature 0.7), Sol (medium reasoning), and Astra (medium reasoning).
- P0: complete tool documentation; P1: the same documentation plus four rules.
- A and B; global, conditional, and null data; five paired seeds (301–305).

This gives **180 formal episodes**. Development seed 9010 supplies 36 separate
protocol checks. All three profiles have an 8,192-token completion cap; reasoning
tokens consume that cap. Reasoning profiles omit temperature. Actual response
model IDs are recorded when returned.

P1 asks the model to compare null/linear baselines, reconcile numerical claims
with evidence, consider complexity and search, and explain whether further
analysis could change its decision. The same rules apply to A and B. They do
not force a tool order or reveal the true pair/gate. P1 also reiterates the JSON
format, so its effects include protocol reliability. Exact text and settings
are in the [frozen protocol](results/model_prompt/protocol.json).

Each episode uses 700 discovery and 300 hidden rows, with five seed-fixed CV
folds. The compared configurations share data, relabeling, splits, and folds.
No hidden score is returned to the AI. Code, prompts, budgets, and randomized
submission order were frozen before execution. There were no automatic retries,
output repairs, or performance-based changes during the run.

## Reproduce or run a new experiment

From the repository root:

```bash
uv sync --frozen --no-install-project
.venv/bin/python -m unittest discover -s experiments/adaptive_analysis -p 'test_*.py'

# Print the full matrix; no credentials, statistical fitting, or API calls.
.venv/bin/python experiments/adaptive_analysis/scripts/run_matrix.py

# Run a statistical reference with no model calls.
.venv/bin/python -m experiments.adaptive_analysis.run --offline --seeds 9001
```

[Rebuild the published results offline](results/model_prompt/README.md) to verify
the completed experiment from saved responses, coefficients, and frozen source.
This does not require an API key or refit models. Historical model outputs cannot
be reproduced by making new stochastic API requests.

For **new billable runs**, configure `OPENROUTER_KEY` in the environment, then:

```bash
# One model/prompt configuration with both workflows and all three conditions.
.venv/bin/python -m experiments.adaptive_analysis.run --execute \
  --profile sol_medium --prompt-variant P1 --seeds 301 302 303 304 305

# Entire matrix, including separate development checks.
.venv/bin/python experiments/adaptive_analysis/scripts/run_matrix.py --execute
```

The current source creates a new configuration hash; the evidence archive retains
the exact source used for the reported run. Raw outputs go under `artifacts/`,
which is ignored by Git. Successful matching episodes are cached; individual
failed episodes require explicit `--retry-failed`, retaining previous attempts.
The published experiment did not use retries.

## How to read the results

Report structure recovery, hidden-set MSE, completion, and resources separately.
Exact structure includes family, pair, gate when applicable, and a descriptive
slope-direction check; it is not causal identification. CV search is exploratory,
not a multiplicity-corrected significance test. A wrong completed selection and
an invalid action are different outcomes.

This compares complete workflows with different evidence volume, statistical
work, model calls, and feedback. It does not isolate feedback alone or establish
superiority over all statistical selection methods. Five seeds per condition and
one model sample per cell support a small descriptive study, not a general model
ranking. See [REPORT.md](REPORT.md) for the observed tradeoffs and limitations.
