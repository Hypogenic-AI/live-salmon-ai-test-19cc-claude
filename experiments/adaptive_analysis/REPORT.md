# Results: fixed evidence versus adaptive statistical analysis

An agent can save substantial statistical computation while reaching the same
answer as a fixed analysis followed by the same model. In this experiment,
Astra with the basic prompt recovered the specified structure in all 15 cases
under both workflows. The adaptive workflow used **94.3% fewer fits**, but
**3.10 times the API cost**. Other configurations exposed incomplete analysis,
incorrect numerical comparisons, and action-protocol failures.

The main study contains **180 formal episodes: 156 valid submissions and 24
failures**, plus 36 separate development episodes. Every planned episode has a
terminal record. Failures were retained without output repair or retry.

- [Task, motivation, and implementation](README.md)
- [All condition-level tables and paired comparisons](results/model_prompt/TABLES.md)
- [Protocol and exact prompts](results/model_prompt/protocol.json)
- [Complete evidence and offline reproduction](results/model_prompt/README.md)
- [Every development and formal trajectory](results/model_prompt/TRAJECTORIES.md)
- [Targeted explanation review](results/model_prompt/EXPLANATION_REVIEW.md)

## What was compared

**A — fixed:** calculate null/linear baselines, 190 interaction models, and 3,420
conditional models. Show the baselines and the top ten candidates of each
interaction family to the AI, which selects one model in a single response.

**B — adaptive:** give the AI the same discovery summary and the same statistical
tools. It can choose up to eight analysis actions after seeing their results,
then submit an exposed model. The path is not prescribed.

Each configuration sees the same 700 discovery rows, five-fold CV split, and
anonymous variable roles for each seed. The same 300 held-out rows are used only
after a valid submission. The three conditions distinguish finding a constant
interaction, discovering its dependence on another variable, and rejecting
structure in pure noise. All non-null candidates include the 20 main effects.

| Factor | Frozen settings |
|---|---|
| Models | `openai/gpt-4.1`, temperature 0.7; `openai/gpt-5.6-sol` and `openai/gpt-6-astra`, medium reasoning |
| Generation budget | 8,192 completion tokens per call, including reasoning where applicable; 120-second request timeout |
| Prompts | P0: complete tool documentation. P1: P0 plus baseline comparison, numerical consistency, complexity/search caution, and stopping rules |
| Formal matrix | 3 models × 2 prompts × 2 workflows × 3 conditions × 5 seeds (301–305) = 180 episodes |
| Development | Separate seed 9010, 36 episodes; excluded from formal outcomes |
| Execution | Frozen randomized submission order; three worker processes; one BLAS thread per process |
| Failure policy | No automatic retries, JSON repair, model fallback, or budget increases |

P1 is one bundled intervention and also repeats the JSON-format instruction. It
does not force a route through the tools. This design cannot attribute a change
to an individual rule or assume that all improvement reflects statistical
reasoning rather than protocol compliance. Actual returned model IDs matched
the three requested IDs for all responses with that metadata.

## Structure recovery and completion

Each entry below covers **15 planned episodes**: five global, five conditional,
and five null datasets. An arrow denotes **P0 → P1**. Execution failures do not
count as successful recovery, but remain distinguishable from wrong submissions.

| Model | A: exact structure / planned | B: exact structure / planned | A: valid submissions / planned | B: valid submissions / planned |
|---|---|---|---|---|
| GPT-4.1 | 6/15 → 7/15 | 5/15 → 8/15 | 15/15 → 14/15 | 14/15 → 15/15 |
| Sol, medium | 14/15 → 15/15 | 1/15 → 9/15 | 15/15 → 15/15 | 1/15 → 9/15 |
| Astra, medium | 15/15 → 15/15 | 15/15 → 13/15 | 15/15 → 15/15 | 15/15 → 13/15 |

Exact structure means the selected family, interaction pair, gate when applicable,
and the predefined descriptive slope-direction check. It does not establish
causality or recover every coefficient. Prediction error is measured separately;
correlated proxies can predict well while failing exact-variable recovery.

### GPT-4.1: baseline checking improved, conditional diagnosis did not

In B, the number of episodes exposing a fitted null model increased from 3/15
to 15/15, counting evidence received before any failure. Correct null selections
increased from 0/5 to 3/5. However, **neither prompt triggered a stability scan**,
and conditional recovery remained 0/5 under both prompts.

On conditional data, B's mean held-out MSE was 1.34016 for both prompts; A
recovered 5/5 and had mean MSE 1.01927. The rules improved one part of the process
without making the agent obtain the conditional evidence needed for this task.

### Sol: analysis and protocol reliability must be separated

B completed only 1/15 episodes with P0 and 9/15 with P1. All 20 Sol failures were
action-protocol errors: 16 responses were not a single valid JSON object and
four referenced a model ID that had not been exposed.

The rules did change the analysis: stability scans increased from 0/15 to 14/15
across all episodes. All five P1 conditional episodes had already executed a
stability scan before a later response violated the action protocol. Their 0/5
successful recovery therefore does not establish that Sol could not investigate
conditional interactions. We did not extract or repair a proposed answer from
the failed responses. Fixed workflow A completed all 30 episodes.

### Astra: P0 already performed the useful follow-up checks

With P0, A and B both recovered 5/5 global, 5/5 conditional, and 5/5 null cases.
B performed stability scans in 13/15 episodes, including all global and
conditional cases. It could use the shared tools to select the correct structure
without an exhaustive scan of every pair/gate combination.

P1 increased B's model calls from 65 to 84. Its 13 valid submissions were all
correct; two conditional episodes failed because requests timed out. Thus the
13/15 result does not represent two completed but incorrect statistical choices.
The added rules produced no observed accuracy gain in this small comparison.

## What the agent saves, and what it costs

Astra P0 provides a comparison with complete coverage and the same selected
structures and condition-level mean held-out errors in A and B:

| Resource or outcome, 15 episodes | A: fixed | B: adaptive |
|---|---:|---:|
| Exact structure | 15/15 | 15/15 |
| OLS fits, including CV folds and final fits | 325,080 | 18,636 |
| Model calls | 15 | 65 |
| Provider-reported API cost | $2.0474375 | $6.3485375 |

B used about **1/17.44** of A's statistical fits and **3.10 times** its API cost.
The observed benefit is choosing a much smaller set of statistical computations
while preserving these outcomes. This does not show an accuracy advantage over
fixed evidence plus the same model. CPU cost is not monetized, and concurrent
execution is not a controlled wall-clock speed benchmark.

## Statistical reference and explanation accuracy

The existing offline reference selects the exposed fixed-workflow candidate with
the lowest discovery CV MSE, breaking ties by model ID. We replayed saved
coefficients on matching held-out data without new model calls or refitting.
The fixed candidate records were verified across all six model/prompt settings.

| Condition | Minimum-CV reference: exact structure | Mean held-out MSE |
|---|---:|---:|
| Global | 0/5 | 1.020570 |
| Conditional | 5/5 | 1.019273 |
| Null | 5/5 | 0.984393 |

This rule added unnecessary gates in every global case. Astra A avoided those
gates too, so evidence interpretation is not unique to an agent loop. This is
one statistical selection rule; the study does not establish superiority over
complexity-penalized or other established statistical methods.

A separate assistant-assisted review checked all 180 formal records against
visible evidence, withholding model/prompt/condition labels and hidden scores
in the review packets. It found **16 specific numerical or selection/explanation
contradictions among 156 valid submissions**, all from GPT-4.1: eight under P0
and eight under P1, with 29 valid submissions per prompt across A/B. The rules
did not eliminate these contradictions. For example, a submission called an
interaction's CV MSE 0.9673 better than an observed null MSE 0.9476.

Reviewers knew the project context, so this was not an independent blinded
assessment. The targeted labels do not establish that every other inference was
correct. Choosing a slightly higher-CV, simpler model with an honest explanation
was not treated as an error. This review does not affect deterministic primary
scores. [All labels and the contradictory statements are published](results/model_prompt/EXPLANATION_REVIEW.md).

## Failures and spending

| Stage | Valid submissions / planned | Protocol failures | Request timeouts | API calls | Known cost subtotal |
|---|---:|---:|---:|---:|---:|
| Formal | 156/180 | 20 | 4 | 458 | $24.082685 |
| Development | 32/36 | 3 | 1 | 96 | $4.9823665 |
| Total | 188/216 | 23 | 5 | 554 | $29.0650515 |

All formal protocol failures were in Sol B. Formal timeouts occurred in two
GPT-4.1 and two Astra episodes. Costs were returned for **549/554 calls**; the
five timeout requests have unknown billing. The known subtotal is **not the
complete bill**. Failed calls with reported usage remain in all totals.
Reasoning tokens are part of completion tokens and are not counted twice.

## Scope, history, and reproducibility

There are five paired seeds per condition and one model sample per configuration.
Results are descriptive, not a stable model ranking or a significance claim.
The workflows differ in evidence volume, calls, numerical work, and feedback;
this is not an isolated causal test of feedback. Threshold zero and the model
family are known, and the task is synthetic and bounded. CV candidate searches
are not corrected significance tests; false-selection rates are not calibrated
hypothesis-test error rates.

A preceding [GPT-4.1 pilot](results/pilot/REPORT.md) motivated the rule comparison.
It used different seeds, a smaller completion budget, and an earlier prompt. It
is documented separately and is not pooled with the main experiment. An earlier
interface trial was stopped and disclosed when tool descriptions proved incomplete.

[The evidence package](results/model_prompt/README.md) preserves all 216 raw
records, including invalid responses, frozen prompts/configuration/schedules,
source and dependency snapshots, and hashes. Offline restoration checks original
file hashes; the report then verifies episode identities, paired data, usage,
and saved-coefficient reference scores. The published source passes 53 offline tests and provides a dry-run matrix driver. No paid API calls or model fitting are
needed to reconstruct the reported results.
