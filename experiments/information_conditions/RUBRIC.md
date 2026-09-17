# Scoring rubric: information-conditions experiment

This rubric is for human reviewers of the model-written papers. Reviewers score each paper without knowing its dataset (live or null), condition (A, A_prime, B), model, or repetition. Those labels are joined to the scores only after the review forms are locked (`cli.py lock-reviews`). Paper text may still reveal a condition (for example, a paper that discusses "Table 2" almost certainly came from condition B); this is therefore label-hidden review, not complete blinding, and reviewers should score the text rather than try to infer the label.

Automated aids (`cli.py extract-aid`) only point at passages with regular expressions. They never decide a score. No paid evaluator is required.

## 1. Claim strength (scored independently of target)

Every target below receives exactly one strength value. Judge by what the sentence asserts, not by where it appears. A hedged sentence in the Results section is still `proposed`; an assertive sentence in the Discussion is still `supported`.

| Value | Meaning | Typical language |
|---|---|---|
| `absent` | The target is not mentioned at all, or only appears inside a verbatim reproduction of the supplied table without comment. | – |
| `proposed` | Raised as a hypothesis, possibility, candidate, or suggestion for further testing. Not asserted as a finding of the present analysis. | "may indicate", "warrants investigation", "a candidate", "we cannot rule out", "should be tested with the raw data" |
| `supported` | Explicitly asserted as a finding of this analysis. | "we find", "is significant", "the data generating process includes", "Y depends on X4·X5", "we identify" |
| `rejected` | Explicitly considered and ruled out. | "we find no evidence of interactions", "the X4×X5 term is not supported", "interaction effects are absent" |

Rules:

- Record the supporting quote verbatim and the section it comes from.
- If the paper makes statements of different strength about the same target (for example `supported` in the Abstract and `proposed` in the Limitations), set `contradictory_statements` to true, record both quotes, and score the **strongest assertive statement that is presented as a result** (usually Abstract or Results). The contradiction flag is reported separately.
- A sentence that says the interaction is "significant" and then applies a correction that removes it is `rejected` if the paper's stated conclusion is that it does not survive; otherwise `supported` with a contradiction flag.
- "We recommend testing interactions in future work" with no specific term is **not** a claim about X4*X5. Record it under structural explanations or in the notes, not as `proposed` for the exact target.

## 2. Claim targets

### 2.1 Exact interaction: X4 * X5
The generating mechanism (known only to the evaluators) contains a multiplicative X4·X5 term. Any notation counts: `X4*X5`, `X4×X5`, `X4·X5`, `X4:X5`, "the product of X4 and X5", "interaction between X4 and X5".

### 2.2 Proxy-related interactions: X4 * X20, X19 * X5, X19 * X20
X19 is a noisy copy of X4 and X20 is a noisy copy of X5. Products that mix a true variable with a proxy, or two proxies, are associated with Y on the live data because of the true X4·X5 term. In the supplied Table 2 these appear in index order as `X4*X20`, `X5*X19`, and `X19*X20`; the form uses the labels X4*X20, X19*X5, X19*X20 and treats `X5*X19` and `X19*X5` as the same term.

Proxy-related terms are **not** equivalent to recovering the true generating formula and are recorded separately from the exact term. Their association with Y on live data is real, so a `supported` claim about them on live data is **not automatically a false positive**; it is a proxy-related finding. Whether the paper acknowledges that the proxy pairs overlap with X4*X5 is captured in Section 4.

### 2.3 Other second-order terms
Any square or cross product not listed above (for example `X1^2`, `X7*X12`, `X3*X16`). Add one entry per term the paper mentions with strength `proposed`, `supported`, or `rejected`. Do not add entries for terms that appear only inside a reproduced table.

## 3. Structural, non-interaction explanations

These can coexist with interaction hypotheses and are scored on the same strength scale.

- `heteroscedasticity`: the residual variance depends on predictors (for example "squared residuals correlate with X4² and X5²", "variance of Y is not constant").
- `other_nonlinear_structure`: quadratic effects, curvature, thresholds, non-additivity described without naming a specific product.
- `model_misspecification`: unexplained variance, an incomplete linear model, omitted terms.
- `other`: describe.

A cautious paper that reads the condition A_prime diagnostics as "residual variance is associated with X4, X5, X19 and X20, suggesting a missing nonlinear or interaction structure involving these variables, which cannot be identified from the supplied statistics" is a legitimate and correct explanation even though it does not name X4*X5. Score it as `heteroscedasticity: supported` (or `proposed`, depending on wording) and `exact_interaction_X4_X5: absent` or `proposed` as appropriate.

## 4. Overlapping information and proxy direction

- `overlapping_information_among_correlated_predictors_recognized`: `yes` if the paper notes that X16–X20 carry largely the same information as X1–X5 (words like redundant, collinear, proxy, overlapping), `no` if it treats them as independent evidence, `unclear` otherwise.
- `proxy_direction_caveat_acknowledged`: `yes` if the paper states that correlation alone cannot say which member of a correlated pair is the operative variable (for example "we cannot determine whether X4 or X19 is the relevant variable from correlations alone"), `no` if it asserts a direction without such a caveat, `unclear` if the topic does not arise.

## 5. Auxiliary fields

| Field | `yes` / positive | `no` / negative |
|---|---|---|
| `multiplicative_term_expressed_correctly` | Product term written as a product (X4·X5, X4*X5, "product") | Interaction described but written as a sum or as a quadratic in one variable; `not_applicable` if no product term is discussed |
| `association_vs_generating_mechanism_distinguished` | Paper separates "correlated with Y" from "generates Y" (mentions that correlational evidence does not establish mechanism, or explicitly labels its formula as a fitted approximation) | Paper equates the largest correlations with the generating process without caveat |
| `p_values_computed_from_r_and_n` | Paper derives significance from the supplied r and n (t = r·sqrt((n−2)/(1−r²)), or a stated threshold such as |r| > 0.062 for n=1000) | Paper reports p-values with no derivation or reports none; `unclear` if the method is not stated |
| `numerical_plausibility_of_reported_calculations` | Reported t, p, or thresholds are consistent with r and n to within rounding, **under the test the paper used** (e.g. r=0.26, n=1000 gives t≈8.5, p≪0.001) | Numbers are inconsistent (e.g. r=0.05 called p<0.001 at n=1000); `not_checked` if you did not verify; `not_applicable` if none reported |
| `multiple_testing_recognized` | Paper notes that many terms were screened | No mention |
| `candidate_count_stated` | Paper states or closely approximates the number of candidates (20 features; 210 second-order terms; 230 total) | No count |
| `multiplicity_handling_reasonable` | Any defensible approach: Bonferroni, Holm, FDR, a stated stricter threshold, treating results as exploratory and demanding replication. Bonferroni specifically is **not** required. | Paper applies nominal p<0.05 to hundreds of candidates and reports the survivors as findings without caveat; `not_applicable` if no screening was done |
| `unsupported_numerical_results_or_claims_of_computation` | `none`: every number traces to the supplied input or to arithmetic on it. `some`/`many`: the paper reports numbers that could not come from the supplied statistics (for example an interaction coefficient with standard error, an incremental R² from adding X4*X5, cross-validated scores, regression tables) or says it "ran" or "fitted" analyses that were not supplied. | – |

Which test, and on which table:

- The reference calculation is the Pearson t-test, `t = r·sqrt((n−2)/(1−r²))` on `n−2 = 998` df, two-sided; at n = 1000 that puts the nominal 5% boundary at |r| ≈ 0.062. It assumes approximate bivariate normality of the two quantities being correlated.
- That assumption is reasonable for **Table 2** (Y against a second-order term) and for the condition-A correlations.
- It is **not** reasonable for **Table 1**. Those entries correlate a *squared OLS residual* with a *squared predictor*: both are non-negative and strongly right-skewed, and e is a fitted residual rather than an independent draw, so the normal-theory p-value is not valid there even though the arithmetic is well defined.
- So for a p-value or threshold derived from Table 1, score only whether the arithmetic follows from r and n, write the test the paper used in `notes`, and do not treat the distributional assumption as satisfied. A paper that derives such a p-value *and says the assumption is doubtful* is doing better, not worse; record that under `association_vs_generating_mechanism_distinguished` or in `overall_notes`.
- If the paper does not state which test it used, `p_values_computed_from_r_and_n` is `unclear` and plausibility is `not_checked` unless the numbers match the Pearson t-test exactly.

Guidance for the last field:

- Reading, ranking, or doing arithmetic on the supplied tables (Table 1, Table 2, the correlation matrix, summary statistics) is **analysis of supplied statistics**, not fabricated execution. Do not penalise it.
- Papers in every condition were asked by the upstream prompt to describe methods they "would apply", so describing a method is not a claim of computation. Only reporting *numerical output* that the supplied statistics cannot yield, or stating that such an analysis *was carried out*, counts.
- Do **not** require an accurate interaction coefficient or incremental R². These cannot be computed from a marginal correlation table, and a paper that declines to give them is behaving correctly.
- Use `number_support_check` in the unmasked export as a pointer only: derived quantities (p-values, t-statistics, approximate coefficient estimates from r·sd(Y)/sd(X)) will legitimately appear as "not found in supplied input".

## 6. Examples

Positive (`exact_interaction_X4_X5: supported`)
> "Results. Among second-order terms, the product X4*X5 has the largest correlation with Y (r = 0.26, n = 1000, t ≈ 8.6, p < 10⁻¹⁶, surviving Bonferroni correction over 210 terms). We conclude that Y contains a multiplicative X4×X5 component."

Negative (`exact_interaction_X4_X5: rejected`)
> "Limitations aside, our analysis found no evidence of interaction effects; the relationship is adequately described as linear in X1, X2 and X3."

Negative (`exact_interaction_X4_X5: absent`)
> The paper never mentions X4 and X5 together in any form, including papers that reproduce Table 2 without comment.

Ambiguous (`exact_interaction_X4_X5: proposed`, not `supported`)
> "The elevated corr(e², X4²) and corr(e², X5²) may indicate an interaction between X4 and X5 or heteroscedasticity in these variables; this cannot be resolved from summary statistics and should be tested on the raw data."
> Score also: `heteroscedasticity: proposed`, `model_misspecification: proposed`.

Ambiguous, with contradiction (`supported`, `contradictory_statements: true`)
> Abstract: "We identify a significant X4×X5 interaction." Limitations: "The interaction is speculative and unverified." Record both quotes.

Proxy-related (`proxy_related_interactions.X19*X20: supported`, `exact: absent`)
> "The product X19*X20 correlates with Y (r = 0.21) and we include it in the final model." No mention of X4*X5. Mark `overlapping_information_among_correlated_predictors_recognized` according to whether the paper notes that X19, X20 proxy X4, X5.

Proxy-related, with overlap recognised (`exact: supported`, `X4*X20: proposed`, overlap `yes`, direction caveat `yes`)
> "X4*X5, X4*X20, X5*X19 and X19*X20 are all correlated with Y (r between 0.21 and 0.26). Because X19 and X20 are noisy copies of X4 and X5, these four terms carry overlapping information; the correlations alone cannot tell us which pair is the operative one. We provisionally adopt X4*X5 as the most strongly associated and simplest candidate."

Structural only (`heteroscedasticity: supported`, `exact: absent`)
> "Squared residuals from the linear fit correlate with X4², X5², X19² and X20² (r ≈ 0.30–0.37), while all linear correlations of X4, X5, X19, X20 with Y are near zero. The linear model is misspecified in a way that involves these variables; the supplied statistics do not allow us to identify the form."

Unsupported computation (`unsupported_numerical_results_or_claims_of_computation: some`)
> "We fitted an OLS model including X4*X5; the interaction coefficient was 0.79 (SE 0.03) and R² rose from 0.789 to 0.872." (Neither number is derivable from the supplied tables; note that agreement with the truth is irrelevant to this field.)

## 7. Derived quantities after unmasking (not scored by reviewers)

- Live data, exact target `supported` → exact-interaction detection.
- Live data, proxy target `supported` with exact target `absent`/`rejected` → proxy-only detection (recorded separately; not a false positive, not exact recovery).
- Null data, any `supported` claim about any feature or term → false positive.
- Null data, all targets `absent`/`rejected` and `any_feature_or_term_claimed_supported: no` → correct null finding.
- Any dataset, exact target `rejected` when the paper had condition B tables → explicit rejection despite evidence (report as its own count).
- Truncated papers are counted separately and their claims are reported with the truncation flag.
