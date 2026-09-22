# Implementation and offline validation

**Status: the fixed-versus-adaptive LLM experiment has not been run.** No model calls or model charges were made. The local execution environment did not have `OPENROUTER_KEY`; the implementation and offline checks are available for review while live development and pilot runs remain pending.

## Implemented

- Paired original, conditional, and null datasets using the base generators.
- A fixed evidence workflow and a bounded feedback workflow sharing statistical tools and the base API client.
- Discovery-only five-fold CV, held-out scoring after submission, and structured evidence references.
- Dry-run and offline-reference modes, explicit failure/retry accounting, and complete candidate/CV fit counts.
- README motivation explaining why the conditional interaction is added and why fixed analysis has the same capability.

## Validation performed

- 36 offline tests passed, including independent scikit-learn numerical comparisons, paired generation, held-out isolation, protocol errors, retry accounting, and unchanged base OLS behavior.
- Default dry-run reports the planned 60 workflows and an upper bound of 300 model calls without making calls or fitting models.
- The missing-key path exits before generating or fitting episodes.
- The full-size offline reference ran all three conditions at development seed 9001: 1,000 rows, 700 discovery, 300 held-out, five CV folds, and one BLAS thread.
- Each condition evaluated 3,612 models: 2 baselines, 190 global interactions, and 3,420 conditional interactions. This required 18,060 CV fits plus 3,612 final fits per condition.
- CLI-generated JSON, CSV, and Markdown reports were checked. Raw generated artifacts remain ignored and can be reproduced.

## Offline reference results — not AI results

The reference automatically selects the exposed candidate with minimum discovery CV MSE. It does not simulate what either LLM workflow would decide. These are three development checks, not a multi-seed effectiveness estimate.

| Condition | Selected family | Test MSE | Exact mechanism | False conditional selection | Fits | Wall seconds |
|---|---|---:|---|---|---:|---:|
| global | conditional | 0.903372 | false | true | 21672 | 15.72 |
| conditional | conditional | 0.896725 | true | n/a | 21672 | 15.89 |
| null | null | 0.882820 | true | false | 21672 | 15.57 |

The minimum-CV reference recovered the planted conditional mechanism and selected the null model on the null dataset. It added an unnecessary conditioning variable on the original global-interaction dataset. This illustrates why predictive error and exact mechanism recovery are reported separately; it is not evidence about an agent.

See [validation.json](validation.json) for configuration, environment, implementation hash, and per-run values. Timings describe this machine and workload only.

## Pending before an AI-comparison claim

1. Configure the local OpenRouter credential and run development seeds with the real model; record any protocol changes before freezing prompts.
2. Freeze the implementation and prompts, then run the 10-seed, three-condition, two-workflow pilot described in README.
3. Report paired accuracy, false selections, failures, tokens, complete reported costs where available, and elapsed time. Include representative successful and failed trajectories.
4. Keep this draft status until real A/B results and limitations have been added.

The inherited client identifies the requested model but does not expose the provider-resolved model/version. The logs therefore keep actual model identity unknown. This pilot will compare complete workflows, not isolate feedback as a single causal factor.
