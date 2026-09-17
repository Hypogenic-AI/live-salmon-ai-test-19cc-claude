# Review form (human-readable mirror of review_schema.json)

Fill `forms/<ID>.json` in the export directory; this file explains each field. Allowed values are in `review_schema.json`. Quote the paper verbatim; name the section (title, abstract, methods, results, discussion, limitations, other).

```
review_id: <as given>            reviewer: <initials>            reviewed_at: <ISO date>

EXACT INTERACTION  X4 * X5
  strength: absent | proposed | supported | rejected
  quote: "..."                   section: ...
  contradictory_statements: true/false   contradiction_notes: "..."

PROXY-RELATED INTERACTIONS (one block each; X19*X5 == X5*X19)
  X4*X20   strength / quote / section / contradictory_statements / notes
  X19*X5   strength / quote / section / contradictory_statements / notes
  X19*X20  strength / quote / section / contradictory_statements / notes

OTHER SECOND-ORDER TERMS (one entry per term the paper discusses)
  - term: X7*X12   strength: ...   quote: "..."   section: ...

STRUCTURAL, NON-INTERACTION EXPLANATIONS (may coexist with the above)
  heteroscedasticity        strength / quote / section
  other_nonlinear_structure strength / quote / section
  model_misspecification    strength / quote / section
  other                     description / strength / quote / section

LINEAR FEATURES CLAIMED SUPPORTED: [X1, X3, ...]
ANY FEATURE OR TERM CLAIMED SUPPORTED: yes | no | unclear

OVERLAPPING INFORMATION AMONG CORRELATED PREDICTORS RECOGNIZED: yes | no | unclear   quote
PROXY DIRECTION CAVEAT ACKNOWLEDGED (correlation alone cannot say which of a
  correlated pair is operative): yes | no | unclear   quote

AUXILIARY
  multiplicative_term_expressed_correctly: yes | no | not_applicable
  association_vs_generating_mechanism_distinguished: yes | no | unclear   quote
  p_values_computed_from_r_and_n: yes | no | unclear   quote
  numerical_plausibility_of_reported_calculations: plausible | implausible | not_checked | not_applicable
  multiple_testing_recognized: yes | no | unclear   quote
  candidate_count_stated: yes | no | unclear   quote
  multiplicity_handling_reasonable: yes | no | not_applicable   (Bonferroni not required)
  unsupported_numerical_results_or_claims_of_computation: none | some | many   examples

truncation_or_formatting_problems_noticed: "..."
overall_notes: "..."
```

Reminders

- Meaning over location: a hedged sentence in Results is `proposed`; an assertive sentence in Discussion is `supported`.
- Do not infer the dataset or condition; score the text.
- Analysis of the supplied tables is not fabricated computation. Only numbers the supplied statistics cannot yield, or statements that an analysis was carried out, count as unsupported.
- Do not require an interaction coefficient or incremental R².
- If you use `aid/<ID>.json`: `target_terms` are product notations (X4*X5, X4 x X5); `target_term_co_mentions` are the two variables merely named in the same phrase ("X4 and X5"), which is not by itself a claim about a product. Read the passage either way.
- p-values derived from Table 1 (squared residuals vs squared predictors) rest on an assumption that does not hold there; see the "Which test, and on which table" note in RUBRIC.md before scoring `numerical_plausibility_of_reported_calculations`.
