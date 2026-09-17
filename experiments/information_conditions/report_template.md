# Information conditions and interaction claims: report template

This file is the **frozen structure** of the report: section order, the six dataset x condition rows in every outcome table, the column definitions, and the scope statements that must survive into the written report. It is covered by the design hash, so the shape of the report cannot change after a freeze.

Every outcome cell here is empty and stays empty. `REPORT.md` is the working copy that gets filled in from `review/formal/<export>/unmasked_summary.csv` after the review forms are locked and unmasked; `REPORT.md` is deliberately **not** in the design hash, because writing up results is not a design change. Smoke-phase papers never enter either file.

## Design

- Question: how do progressively richer statistical summaries (A → A_prime → B) change what one LLM claims about a known X4·X5 interaction on the live dataset and about null data on the dead dataset?
- Model: one identifier from the upstream configuration, recorded in `inputs/manifest.json` (`model.id`) and in every run record as `requested_model`, together with the provider's returned model string.
- Datasets: the two fixed upstream datasets (1000 rows, 20 predictors), regenerated with the upstream generator and unchanged seed, verified against the committed samples and baselines (`inputs/manifest.json`, `dataset_verification`).
- Conditions: A = upstream summary unchanged; A_prime = A + OLS in-sample R², n, corr(e², Xi²) for X1–X20 (no coefficients); B = A_prime + Pearson r with Y for all 210 second-order terms in fixed index order (raw r and n only).
- Phases: smoke = 1 call per dataset × condition (6 calls); formal = 5 calls per dataset × condition (30 calls). Shuffled schedule with recorded scheduling seed. Repetitions are independent samples at the upstream temperature; no provider seed is passed.
- Scoring: human review with `RUBRIC.md`, label-hidden export, claim extraction locked before unmasking.

## Execution status

| Phase | Freeze file | Executed at | Planned | Completed | Refused | Failed | Truncated |
|---|---|---|---|---|---|---|---|
| smoke | | | 6 | | | | |
| formal | | | 30 | | | | |

## Results

Formal phase only. "Completed" counts successful responses; "Refused" counts calls the provider answered with an explicit refusal (a `message.refusal`, or a content-filter finish reason) — a recorded outcome, never retried and never scored as a paper; "Failed" counts records whose bounded retries were exhausted or that failed permanently; "Truncated" counts completed responses whose finish reason indicates the output limit was hit.

| Dataset | Condition | Planned formal calls | Completed | Refused | Failed | Truncated | Model mismatch flagged |
|---|---|---|---|---|---|---|---|
| live_salmon | A | 5 | | | | | |
| live_salmon | A_prime | 5 | | | | | |
| live_salmon | B | 5 | | | | | |
| dead_salmon | A | 5 | | | | | |
| dead_salmon | A_prime | 5 | | | | | |
| dead_salmon | B | 5 | | | | | |

Claim counts per combination (out of completed papers). Strength values follow `RUBRIC.md`; proxy-related terms are X4*X20, X19*X5, X19*X20 and are not equivalent to exact recovery.

| Dataset | Condition | X4*X5 supported | X4*X5 proposed | X4*X5 rejected | Proxy-related supported | Proxy-related proposed | Other 2nd-order supported | Structural explanation proposed or supported | Overlap recognized | Proxy-direction caveat | Any term claimed supported | Contradictory statements |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| live_salmon | A | | | | | | | | | | | |
| live_salmon | A_prime | | | | | | | | | | | |
| live_salmon | B | | | | | | | | | | | |
| dead_salmon | A | | | | | | | | | | | |
| dead_salmon | A_prime | | | | | | | | | | | |
| dead_salmon | B | | | | | | | | | | | |

Auxiliary fields (multiplicative term expressed correctly, association vs. mechanism, p-values from r and n, numerical plausibility, multiple-testing recognition, candidate count, multiplicity handling, unsupported computation) will be summarised per combination in `review/formal/<export>/unmasked_summary.csv` and discussed below once available.

Interpretation: (written in REPORT.md after unmasking; this template carries no interpretation).

## Scope and interpretation constraints

- This experiment uses one model, two fixed datasets, and five formal repetitions per combination. It provides no estimate of general performance across datasets, data-generating processes, or models.
- Across conditions, input length, information, and analysis cues change together. A difference between conditions cannot be attributed to information content alone.
- The supplied tables use fixed numeric ordering, which introduces possible position effects (for example, X1 terms appear first and X20 terms last).
- The supplied summaries do not guarantee identification of the true mechanism. Marginal correlations with second-order terms cannot separate X4*X5 from its proxy-related terms, and residual diagnostics cannot distinguish an interaction from heteroscedasticity.
- The model is requested by identifier through OpenRouter. An unchanged model identifier does not guarantee an unchanged backend; the provider's returned model string and provider name are recorded per call.
- Differences from historical results (the upstream 0/9 interaction detections) cannot by themselves establish model drift, because prompts, dates, provider routing, and sample size all differ.
- Repetitions are not seed-controlled: no provider seed is passed, and this is recorded in `config.json`.
- Failures, refusals and truncations are reported separately from claim counts and are never retried on the basis of content. An explicit refusal is counted in its own column and excluded from the denominator of claim counts, not recorded as an absent claim.
- Review is label-hidden, not fully blind: paper content can reveal its condition.

## Failures, refusals and truncations

Reported separately from results. Filled from `runs/formal/summary.json` (including its `refusals` list) and the per-record `attempts` lists. `Outcome` is one of `failed`, `refused` or `truncated`; for a refusal, `Notes` carries the refusal reason and text.

| Phase | Record | Dataset | Condition | Rep | Outcome | Attempts | Notes |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

## Changes since the design freeze

See `CHANGES.md`. Any change after the smoke phase requires a new documented freeze before formal execution.
