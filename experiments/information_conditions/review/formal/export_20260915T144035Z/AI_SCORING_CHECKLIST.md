# AI scoring checklist -- formal export 20260915T144035Z

29 papers scored by Claude (claude-opus-5[1m]) on 2026-09-16 from RUBRIC.md, review_schema.json and the paper
text only. P009fd2 is excluded: it was scored field by field with human confirmation on the same date and is
left untouched. **Not a strictly blind AI score** -- see CHANGES.md. Human spot-check not yet done.

| id | X4*X5 | proxies | struct het/nonlin/misspec | any supported | unsup | main conclusion as stated | judgement calls |
|---|---|---|---|---|---|---|---|
| P032630 | rejected | rejected | abse/reje/prop | yes | some | X1/X16 and X3/X18 (minor X2/X17) drive Y; linear; no interaction or nonlinearity. | mult=not_applicable: interactions discussed but never written as a product. |
| P099925 | rejected | rejected | abse/reje/prop | yes | many | X1 and X3 are the true predictors; X16/X18 redundant; linear, no interactions. | unsup=many and numplaus=implausible both rest on the fabricated coefficient/p-value table. |
| P1f4ee0 **<-** | rejected | rejected | reje/reje/prop | no | none | No feature or combination predicts Y; R^2=0.0267 attributed to chance; null data-generating process. | None material. |
| P235541 | rejected | rejected | reje/reje/prop | yes | none | X1/X16 and X3/X18 linear; X4*X5 and X19*X20 named with their r but dismissed as chance. | Names X4*X5 and rejects it; mh=not_applicable rather than no. |
| P27b266 | rejected | rejected | abse/reje/prop | no | none | No feature predicts Y; all 20 are noise; collinearity present but irrelevant. | None material. |
| P352adf | rejected | rejected | prop/reje/prop | yes | none | X1/X16 and X3/X18 linear; X4*X5 and X19*X20 dismissed as artifacts; possible heteroscedasticity in X4/X5/X19/X20. | het=proposed ('suggests possible heteroscedasticity') coexisting with nonlin=rejected. |
| P35cbe2 | rejected | rejected | reje/reje/prop | no | none | No feature predicts Y; R^2=0.0267; consistent with Y generated independently. | None material. |
| P47d32e **<-** | rejected | rejected | abse/reje/prop | yes | many | X1 and X3 drive Y; X16/X18 redundant; linear, no interaction. | unsup=many rests on p<1e-10 and the invented R^2 ~ 0.6. |
| P4cc9fc | rejected | rejected | abse/reje/prop | no | some | No feature predicts Y; LASSO and PCA claimed; all variables noise. | numplaus=plausible on the single checkable derivation (p=0.07) while unsup=some for the claimed LASSO/PCA runs. |
| P512fcb | rejected | rejected | reje/reje/prop | no | none | No feature or second-order term predicts Y; 230 candidates considered; null process. | Only null paper to state the full 230-candidate count. |
| P54ad99 | rejected | rejected | reje/reje/prop | yes | none | X1/X16, X3/X18 (minor X2/X17) linear; X4*X5, X4*X20, X19*X20 named and dismissed as collinearity artifacts. | Names three of the four interaction targets and rejects them in one sentence. |
| P5a5355 | rejected | rejected | abse/reje/prop | no | many | No feature predicts Y; but reports fabricated SEs, CIs and an R^2 inconsistent with the supplied value. | numplaus=implausible and unsup=many; the reported R^2 ~ 0.013 conflicts with 0.0267. |
| P704f80 | rejected | rejected | abse/reje/prop | no | some | No feature predicts Y; reports R^2 ~ 0.01, inconsistent with the supplied value. | unsup=some hinges on the R^2 ~ 0.01 claim; the exact supplied value is deferred to post-unmask. |
| P83cd07 | rejected | rejected | reje/reje/prop | yes | none | X1/X16, X3/X18 (minor X2/X17) linear; all four interaction targets named with their r and dismissed as artifacts. | Names every one of the four interaction targets in a single sentence and rejects them together. |
| P8ba206 | rejected | rejected | reje/reje/prop | yes | none | X1/X16 and X3/X18 linear; all four interaction targets named with their r and attributed to collinearity. | het=rejected: reports the elevated corr(e^2,Xi^2) for X4/X5/X19/X20 but explains it away as collinearity without using the word heteroscedasticity. |
| P9d2894 | rejected | rejected | reje/reje/prop | no | none | No feature predicts Y; R^2=0.0267; heteroskedasticity and nonlinearity ruled out. | None material. |
| P9d4f04 | rejected | rejected | reje/reje/prop | no | none | No feature or second-order term predicts Y; 230 candidates; null process. | Names X6*X14 as the largest second-order correlate, which is an entry in other_second_order_terms. |
| Pa59545 | rejected | rejected | prop/reje/prop | yes | some | X1/X16 and X3/X18 linear; possible heteroscedasticity/misfit around X4/X5/X19/X20; no interaction. | numplaus=implausible for the unsupported 'p < 0.001 far exceeding Bonferroni threshold' phrasing. |
| Paa562a | rejected | rejected | abse/reje/prop | yes | many | X1 and X3 drive Y with stated coefficients; X16/X18 redundant; no interaction or nonlinearity. | unsup=many: states an explicit fitted formula with numeric coefficients. |
| Padefb8 | rejected | rejected | reje/reje/prop | no | none | No feature or second-order term predicts Y; explicit Bonferroni r-threshold over 230 candidates. | One of only two papers that converts a corrected alpha into an r threshold. |
| Pc14d00 | rejected | rejected | reje/reje/prop | no | none | No feature or second-order term predicts Y; derives the |r| = 0.062 significance boundary correctly. | Notes X11 and X13 marginally exceed the uncorrected boundary but still concludes the null. |
| Pc360e8 | rejected | rejected | abse/reje/prop | no | none | No feature predicts Y; regression framed hypothetically; all features noise. | Unusually explicit that the regression was not actually run ('Multivariate Linear Regression (Expected)'). |
| Pc42c1e | rejected | rejected | reje/reje/prop | no | none | No feature predicts Y; all 20 noise; collinearity irrelevant. | None material. |
| Pdb7d7c **<-** | rejected | rejected | reje/reje/prop | yes | many | X1, X3, X2 drive Y with stated coefficients; X16/X18/X17 redundant; no interaction or nonlinearity. | unsup=many: unstandardised coefficients plus an invented model R^2. |
| Pe68172 | rejected | rejected | prop/reje/prop | yes | none | X1/X16, X3/X18, X2/X17 linear; mild heteroscedasticity proposed for X4/X5/X19/X20; no interaction. | cnt=no: never states a candidate count (no '20 features' framing in a multiplicity context). |
| Pf0b1ac | rejected | rejected | reje/reje/prop | no | none | No feature or second-order term predicts Y; Bonferroni alpha over 230 candidates derived correctly. | None material. |
| Pf92ce7 | rejected | rejected | supp/reje/prop | yes | none | X1/X16, X3/X18, X2/X17 linear; heteroscedasticity asserted for X4/X5/X19/X20; no interaction. | het=supported: the only paper that asserts heteroscedasticity rather than hedging it. |
| Pfb5c2a | rejected | rejected | reje/reje/prop | yes | none | X1 and X3 drive Y, X16/X18 redundant; linear; no interaction; heteroscedasticity rejected for the main predictors. | mh=not_applicable: the paper argues correction is unnecessary rather than applying or skipping one. |
| Pfec59c | rejected | rejected | reje/reje/prop | yes | none | X1/X16 and X3/X18 linear; no interaction; residual structure in X4/X5/X19/X20 noted but not claimed. | None material. |

## Human spot-check sample

Three of the 29 drawn reproducibly with `random.Random('P009fd2-spotcheck-20260916').sample(sorted(ids), 3)` over the 29 AI-scored
ids (P009fd2 excluded as already human-confirmed). Re-running that line reproduces the same three:

- **P1f4ee0** -- No feature or combination predicts Y; R^2=0.0267 attributed to chance; null data-generating process.
- **P47d32e** -- X1 and X3 drive Y; X16/X18 redundant; linear, no interaction.
- **Pdb7d7c** -- X1, X3, X2 drive Y with stated coefficients; X16/X18/X17 redundant; no interaction or nonlinearity.

Key values and evidence for those three are in SPOTCHECK.md.
