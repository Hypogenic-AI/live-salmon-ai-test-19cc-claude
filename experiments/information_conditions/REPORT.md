# Information conditions and interaction claims: report

The formal experiment was completed on 2026-09-15 under `formal_20260915T142345Z.json`. Review forms were locked and unmasked on 2026-09-17. Smoke-phase papers are excluded from all results below.

The formal phase contained 30 papers: five repetitions for each of three conditions on each of two datasets. One paper was reviewed field by field by a human. The remaining 29 papers were scored by Claude (`claude-opus-5[1m]`); three of those were spot-checked by a human on nine of their 22 fields, and all spot-checked values were retained. The results below should therefore be read as AI-assisted classifications of the claims made in the papers.

## Design

- **Question:** How do progressively richer statistical summaries change what one language model claims about a known `X4·X5` interaction in the live dataset and about null data in the dead dataset?
- **Model:** `openai/gpt-4.1`, recorded in `inputs/manifest.json` and in every run record together with the provider's returned model string.
- **Datasets:** Two fixed 1,000-row datasets with 20 predictors. Because the upstream repository does not commit the full CSV files, they were regenerated with the upstream generator and seed, then checked against the committed samples and baseline statistics.
- **Conditions:** A is the unchanged upstream summary. A_prime adds the OLS in-sample R², sample size, and `corr(e², Xi²)` for `X1`-`X20`. B adds Pearson correlations between `Y` and all 210 second-order terms, using raw correlations and sample sizes only.
- **Phases:** The smoke phase used one call per dataset-condition combination. The formal phase used five calls per combination. The call order was shuffled with a recorded scheduling seed. No provider seed was supplied.
- **Scoring:** Papers were exported with random IDs and shuffled order. The rubric was applied before the mapping was unmasked.

## Execution status

| Phase | Freeze file | Executed at | Planned | Completed | Refused | Failed | Truncated |
|---|---|---|---:|---:|---:|---:|---:|
| smoke | `smoke_20260915T140534Z.json` | 2026-09-15 | 6 | 6 | 0 | 0 | 0 |
| formal | `formal_20260915T142345Z.json` | 2026-09-15 | 30 | 30 | 0 | 0 | 0 |

## Results

The results below use the formal phase only. "Completed" means that the model returned a response that could be reviewed. "Refused" means that the provider returned an explicit refusal. "Failed" means that all bounded retries were exhausted. "Truncated" means that the response reached the output limit.

| Dataset | Condition | Planned formal calls | Completed | Refused | Failed | Truncated | Model mismatch flagged |
|---|---|---:|---:|---:|---:|---:|---:|
| live_salmon | A | 5 | 5 | 0 | 0 | 0 | 0 |
| live_salmon | A_prime | 5 | 5 | 0 | 0 | 0 | 0 |
| live_salmon | B | 5 | 5 | 0 | 0 | 0 | 0 |
| dead_salmon | A | 5 | 5 | 0 | 0 | 0 | 0 |
| dead_salmon | A_prime | 5 | 5 | 0 | 0 | 0 | 0 |
| dead_salmon | B | 5 | 5 | 0 | 0 | 0 | 0 |

Claim counts are calculated among completed papers. The proxy-related terms are `X4*X20`, `X19*X5`, and `X19*X20`; they are not treated as equivalent to the exact `X4*X5` interaction.

| Dataset | Condition | X4*X5 supported | X4*X5 proposed | X4*X5 rejected | Proxy-related supported | Proxy-related proposed | Other 2nd-order supported | Structural explanation proposed or supported | Overlap recognized | Proxy-direction caveat | Any term claimed supported | Contradictory statements |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| live_salmon | A | 0/5 | 0/5 | 5/5 | 0/5 | 0/5 | 0/5 | 5/5 | 5/5 | 5/5 | 5/5 | 0/5 |
| live_salmon | A_prime | 0/5 | 0/5 | 5/5 | 0/5 | 0/5 | 0/5 | 5/5 | 5/5 | 5/5 | 5/5 | 0/5 |
| live_salmon | B | 0/5 | 0/5 | 5/5 | 0/5 | 0/5 | 0/5 | 5/5 | 5/5 | 5/5 | 5/5 | 0/5 |
| dead_salmon | A | 0/5 | 0/5 | 5/5 | 0/5 | 0/5 | 0/5 | 5/5 | 5/5 | 0/5 | 0/5 | 0/5 |
| dead_salmon | A_prime | 0/5 | 0/5 | 5/5 | 0/5 | 0/5 | 0/5 | 5/5 | 5/5 | 0/5 | 0/5 | 0/5 |
| dead_salmon | B | 0/5 | 0/5 | 5/5 | 0/5 | 0/5 | 0/5 | 5/5 | 5/5 | 0/5 | 0/5 | 0/5 |

The structural explanation field includes any paper that proposed or supported heteroscedasticity, another nonlinear structure, or model misspecification. It is 5/5 in every cell because most papers included a general limitation stating that the supplied statistics could not rule out more complex structure. Heteroscedasticity is therefore reported separately.

| Dataset | Condition | Heteroscedasticity proposed or supported |
|---|---|---:|
| live_salmon | A | 0/5 |
| live_salmon | A_prime | 3/5 |
| live_salmon | B | 1/5 |
| dead_salmon | A | 0/5 |
| dead_salmon | A_prime | 0/5 |
| dead_salmon | B | 0/5 |

Auxiliary fields are summarized below. The numerical-plausibility values in the first table are the locked values. Corrections made after unmasking are listed separately.

| Dataset | Condition | p from r and n | Numerically plausible | Implausible | Multiple testing recognized | Candidate count stated | Multiplicity handling reasonable | Association distinguished from mechanism | Unsupported computation: none / some / many |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| live_salmon | A | 0/5 | 0/5 | 4/5 | 5/5 | 5/5 | 5/5 | 0/5 | 0 / 1 / 4 |
| live_salmon | A_prime | 0/5 | 0/5 | 1/5 | 5/5 | 2/5 | 1/5 | 0/5 | 4 / 1 / 0 |
| live_salmon | B | 0/5 | 0/5 | 0/5 | 5/5 | 5/5 | 0/5 | 0/5 | 5 / 0 / 0 |
| dead_salmon | A | 0/5 | 1/5 | 1/5 | 5/5 | 5/5 | 5/5 | 0/5 | 2 / 2 / 1 |
| dead_salmon | A_prime | 1/5 | 1/5 | 0/5 | 5/5 | 5/5 | 5/5 | 0/5 | 5 / 0 / 0 |
| dead_salmon | B | 3/5 | 3/5 | 0/5 | 5/5 | 5/5 | 5/5 | 0/5 | 5 / 0 / 0 |

Three numerical-plausibility judgments were corrected after unmasking when the reported rounding was recomputed. The locked forms were not overwritten.

| Dataset | Condition | Plausible, locked → corrected | Implausible, locked → corrected |
|---|---|---:|---:|
| live_salmon | A | 0 → 0 | 4 → 4 |
| live_salmon | A_prime | 0 → 0 | 1 → 1 |
| live_salmon | B | 0 → 0 | 0 → 0 |
| dead_salmon | A | 1 → 0 | 1 → 2 |
| dead_salmon | A_prime | 1 → 1 | 0 → 0 |
| dead_salmon | B | 3 → 1 | 0 → 2 |

These corrections affect only the auxiliary numerical-plausibility field. No primary result changes.

### Interpretation

No paper treated the exact `X4*X5` interaction as a supported or proposed finding. This was true in all six dataset-condition combinations.

The field `exact_interaction_X4_X5` is marked `rejected` in all 30 forms. Under the rubric, a general statement such as "there is no evidence of interaction effects" counts as a rejection of the specific target, even when the paper does not name `X4*X5`. Therefore, the 30/30 figure does not mean that every paper explicitly tested and ruled out that product term.

The clearest direct comparison is the live-data B condition. All five papers named `X4*X5` and reported its correlation. In the supplied table, this was the largest of the 210 second-order correlations, at `r = 0.2639`.

All five live-data B papers acknowledged the multiple-comparison problem, but none used a valid correction to justify rejecting `X4*X5`. With `n = 1000`, a two-sided Pearson test with Bonferroni correction over the 210 second-order terms gives a threshold of approximately `|r| > 0.116`. Including the 20 main effects changes the threshold only slightly, to approximately `|r| > 0.117`. The observed correlation of `0.2639` is well above either threshold. Under the Pearson approximation, its uncorrected p-value is approximately `2.1 × 10⁻¹⁷`, and its Bonferroni-adjusted p-value is approximately `4.5 × 10⁻¹⁵`.

The live-data B rejections therefore were not the result of a valid multiple-comparison correction. This does not prove that the model followed a particular internal rule, but it shows that the stated rejections were not supported by the correction they might have invoked.

Two recurring reasons for rejecting `X4*X5` are difficult to reconcile with the supplied evidence. First, describing the correlation as a chance result is not consistent with `r = 0.2639` at `n = 1000`, which remains far beyond the Bonferroni threshold. Second, the absence of marginal associations for `X4` and `X5` does not rule out their interaction. In this synthetic data-generating process, `Y` contains a pure `X4*X5` term, so the marginal correlations of `X4` and `X5` with `Y` are expected to be close to zero.

Collinearity remains a legitimate limitation for identifying which related product term generated the association. The supplied statistics do not by themselves distinguish `X4*X5` from the proxy-related terms. However, collinearity is not evidence that the observed association is absent.

No paper supported a proxy-related product term. The distinction between the exact term and its proxy-related terms was therefore not used to identify a positive claim.

The main change across conditions concerned structural explanations. On the live dataset, heteroscedasticity was proposed or supported in 0/5 papers under A, 3/5 under A_prime, and 1/5 under B. The A_prime papers received residual diagnostics but not the second-order table. Three interpreted the elevated values for `X4`, `X5`, `X19`, and `X20` as possible non-constant variance. Under B, the same pattern was more often interpreted as collinearity. These papers identified residual structure, but none connected it to a specific interaction term.

The dead dataset produced no positive feature or term claims. `Any term claimed supported` was 0/5 in all three dead-data conditions.

On the live dataset, the papers frequently identified `X1`/`X16` and `X3`/`X18` as the main linear signals. `X2` and `X17` appeared in some papers as weaker secondary predictors. Individual linear features were not separate scored targets in this experiment, so no X2-specific rate is reported and the upstream 67% figure is not directly comparable to these results.

Papers also reported fewer unsupported numerical analyses as more relevant statistics were supplied. Condition A does not provide R², residual diagnostics, or the second-order table. Five condition-A papers nevertheless reported an R², two reported coefficient tables with p-values, and one claimed to have inspected residual plots. Both B cells were 5/5 for `none` in the unsupported-computation field. This is an association across three conditions with five papers per cell, not evidence that the additional statistics caused the change.

The numerical-derivation counts use two related but different scopes. In the locked review field `p_values_computed_from_r_and_n = yes`, four papers are included: P009fd2, Padefb8, Pc14d00, and Pf0b1ac. Two of these calculations are correct and two are incorrect after correction.

The post-unmask verification document examined a different set of four papers: P4cc9fc, Padefb8, Pc14d00, and Pf0b1ac. P009fd2 had already been checked during the human-confirmed review, while P4cc9fc printed a checkable p-value but was marked `unclear` in the rubric field. Among the four calculations rechecked in that post-unmask pass, one was correct and three were incorrect. These statements use different denominators and should not be presented as the same count.

Representative passages from the five live-data B papers show how the rejections were stated:

- **P235541:** "The only second-order term with correlation |r| > 0.25 is X4*X5 (r = 0.2639) and X19*X20 (r = 0.2120), but X4/X5/X19/X20 themselves are not predictive of Y, suggesting this is due to chance or secondary structure rather than a true interaction relevant to Y."
- **P352adf:** "The largest correlation between Y and any second-order term is for X4*X5 (r = 0.26) and X19*X20 (r = 0.21), but these features themselves are not predictive of Y (|r| < 0.02 for each)."
- **P54ad99:** "Only X4*X5 (r = 0.264), X4*X20 (r = 0.222), and X19*X20 (r = 0.212) approach moderate correlations. However, these are likely artifacts of collinear variables, not genuine interaction effects."
- **P83cd07:** "but these involve features that have negligible direct associations with Y and are highly collinear, suggesting these are statistical artifacts, not genuine interaction effects."
- **P8ba206:** "These reflect the underlying collinearity and do not indicate strong, independent nonlinear or interaction effects."

The reasons given are not mutually exclusive. Absent marginal associations are invoked by P235541, P352adf, and P83cd07; collinearity is invoked by P54ad99, P83cd07, and P8ba206. P83cd07 gives both in one sentence.

The A_prime papers used similar language when interpreting the residual diagnostics. These are the three live-data A_prime papers that proposed or supported heteroscedasticity:

- **Pa59545:** "this pattern likely reflects model misfit (possible nonlinearity or heteroskedasticity) related to these collinear pairs"
- **Pe68172:** "show moderate correlations, suggesting that residual variance increases with these predictors’ magnitude (possible heteroscedasticity or missing higher-order terms)."
- **Pf92ce7:** "the correlation suggests their values are associated with non-constant residual variance (heteroscedasticity), possibly implying a variance effect or omitted nonlinear term."

## Scope and interpretation constraints

- This experiment uses one model, two fixed datasets, and five formal repetitions per combination. It does not estimate performance across models, datasets, or data-generating processes.
- Information, input length, and analysis cues change together across conditions. Differences between conditions cannot be attributed to information content alone.
- The supplied tables use a fixed numeric order, which may introduce position effects.
- The summaries do not guarantee identification of the true mechanism. Correlations with second-order terms cannot separate `X4*X5` from proxy-related terms, and residual diagnostics cannot distinguish an interaction from heteroscedasticity.
- An unchanged model identifier does not guarantee an unchanged backend. The returned model and provider are recorded for each call.
- Differences from the upstream results cannot by themselves establish model drift because the prompts, dates, provider routing, and sample sizes differ.
- Repetitions are not seed-controlled because no provider seed was supplied.
- Failures, refusals, and truncations are reported separately from claim counts. Refusals are excluded from the paper denominator and are not treated as absent claims.
- The review was label-hidden rather than fully blind. Paper text could reveal the condition or dataset. Thirteen of the 30 papers quoted a neutral dataset label, and eight referred to the second-order table or to "210 terms."
- Scoring was predominantly AI-assisted. Claude completed 29 forms, one form was confirmed field by field by a human, and three AI-completed forms were spot-checked on nine fields each. Twenty-six forms received no human review.
- The scoring process was not strictly blind. The identities of 13 papers were visible earlier in the session while label leakage was being measured. During scoring, only the paper text was used; the mapping, run records, and input files were not opened.
- With five repetitions per cell, a result of 0/5 or 5/5 still permits a wide range of underlying rates. Differences of one or two papers between cells should not be interpreted as stable effects.
- The six cells should not be pooled into a single failure rate because they differ both in condition and in whether the dataset contains signal.
- Three auxiliary numerical-plausibility values were corrected after unmasking. The corrections are documented in `review/formal/export_20260915T144035Z/VERIFICATION_POST_UNMASK.md`; no primary count changed.
- The full 1,000-row datasets were regenerated because the upstream files are gitignored. The regenerated files matched the committed samples and baseline statistics, but the original full files were not available for direct byte comparison.

## Failures, refusals and truncations

No failure, refusal, or truncation occurred in the formal phase. One transient network error occurred during `dead_salmon/B`, repetition 5. The call succeeded on the next attempt, and both attempts remain in the record.

| Phase | Record | Dataset | Condition | Rep | Outcome | Attempts | Notes |
|---|---|---|---|---:|---|---:|---|
| formal | retained in run record | dead_salmon | B | 5 | success | 2 | First attempt ended with a connection error; second attempt succeeded. |

## Changes since the design freeze

The experiment was executed under the original smoke and formal freezes. The initial post-run review identified four categories of defects: manifest reproducibility, review-pipeline validation, malformed-response handling, and report validation. A later re-review found two additional branch defects involving preservation of existing regenerated datasets and validation of the resolved model identifier. `CHANGES.md` is the authoritative list; the six categories named here correspond one to one with the entries recorded there.

These fixes were made after the formal run and did not modify the historical experiment. The formal schedule contains 30 unique cache keys and 30 records. All 30 formal responses passed the response parser; none entered the malformed-response path. The formal records contain no duplicate calls, and the review export contains 30 unique papers and 30 matching forms. Both datasets were present and passed verification before execution, and every formal record reports the requested and returned model as `openai/gpt-4.1`.

The original freeze files, inputs, run records, and review lock remain unchanged. The current working tree requires a new freeze for any future execution, but the historical results remain attributed to the design under which they were run. No new run was made under the corrected code.

The current test suite contains 94 passing tests. The fixes and their regression tests are documented in `CHANGES.md`.

Post-unmask numerical verification is documented in `review/formal/export_20260915T144035Z/VERIFICATION_POST_UNMASK.md`. The locked forms remain unchanged; the three auxiliary corrections are recorded separately.
