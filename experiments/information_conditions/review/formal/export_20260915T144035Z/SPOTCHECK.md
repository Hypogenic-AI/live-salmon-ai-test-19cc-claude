# Human spot-check -- 3 of the 29 AI-scored papers

Drawn with `random.Random('P009fd2-spotcheck-20260916').sample(sorted(ids), 3)` over the 29 AI-scored ids.
Scored by Claude (claude-opus-5[1m]) on 2026-09-16; **not human-verified and not a strictly blind score**.
Only the fields most likely to be contested are listed -- the full 22 are in each form.

## P1f4ee0

Paper: `papers/P1f4ee0.md` | Form: `forms/P1f4ee0.json`

| field | value | verbatim evidence |
|---|---|---|
| X4*X5 | `rejected` | No evidence of interaction effects: neither individual features nor their combinations are predictive of Y. |
| proxy X4*X20 | `rejected` | No evidence of interaction effects: neither individual features nor their combinations are predictive of Y. |
| heteroscedasticity | `rejected` | Correlations between squared residuals and squared predictors (max r=0.1049 for X12, most \|r\| < 0.04) are weak, suggesting no substantial nonlinear effects. |
| model_misspecification | `proposed` | Hidden Nonlinear/Interaction Effects:** Although no evidence was found, extremely complex or higher-order nonlinearities (beyond individual Xi² terms or pairwise interactions) could go undetected, but are implausible given the flat diagnostics. |
| overlap recognised | `yes` | The extremely high inter-feature correlations in some pairs (e.g., X4-X19, X1-X16) suggest that the Xs are not all independent, but this is irrelevant for Y, as neither the features individually nor in highly correlated pairs show any association with the outcome. |
| proxy direction caveat | `unclear` |  |
| p from r and n | `unclear` | which is not significant at n=1000 after correcting for multiple comparisons |
| numerical plausibility | `not_checked` | Asserts non-significance at n=1000 after correction but shows no r-to-p step, so there is no derivation to check. |
| unsupported computation | `none` | States 'All conclusions are based strictly on the supplied statistics, without external model fitting.' |

Linear features claimed supported: `[]` | any term supported: `no` | other second-order entries: `[]`

## P47d32e

Paper: `papers/P47d32e.md` | Form: `forms/P47d32e.json`

| field | value | verbatim evidence |
|---|---|---|
| X4*X5 | `rejected` | No interaction or quadratic terms (e.g., X1*X3, X1²) were significant after Bonferroni correction. |
| proxy X4*X20 | `rejected` | No interaction or quadratic terms (e.g., X1*X3, X1²) were significant after Bonferroni correction. |
| heteroscedasticity | `absent` |  |
| model_misspecification | `proposed` | If the true data generating process includes higher-order or interaction terms that are not detectable from correlations and linear regression, these may be missed. |
| overlap recognised | `yes` | The presence of strong inter-feature correlations suggests that the true data generating process uses just a few latent variables, which are redundantly measured by multiple observed features. |
| proxy direction caveat | `yes` | with X1/X16 and X3/X18 being nearly interchangeable due to high collinearity |
| p from r and n | `no` | With 20 features, the Bonferroni-corrected significance threshold is p < 0.0025. |
| numerical plausibility | `implausible` | Reports 'p < 1e-10' for X1 and X3 and an estimated R^2 ~ 0.6 'from sum of squared correlations minus collinearity overlap'; neither is derivable and no derivation is shown. |
| unsupported computation | `many` | Standardised betas with p < 1e-10, an invented model R^2 ~ 0.6, and claims of having run stepwise selection, VIF analysis, partial residual plots and added-squares plots. |

Linear features claimed supported: `['X1', 'X3', 'X16', 'X18']` | any term supported: `yes` | other second-order entries: `['X1*X3']`

## Pdb7d7c

Paper: `papers/Pdb7d7c.md` | Form: `forms/Pdb7d7c.json`

| field | value | verbatim evidence |
|---|---|---|
| X4*X5 | `rejected` | No strong evidence for interaction terms (e.g., X1*X3, X2*X3) or nonlinear effects (e.g., X1^2) based on added-variable plots and regression diagnostics. |
| proxy X4*X20 | `rejected` | No strong evidence for interaction terms (e.g., X1*X3, X2*X3) or nonlinear effects (e.g., X1^2) based on added-variable plots and regression diagnostics. |
| heteroscedasticity | `rejected` | Residual plots confirmed homoscedasticity and linearity. |
| model_misspecification | `proposed` | We ruled out simple nonlinearity and pairwise interactions, but cannot exclude more complex nonlinear or higher-order interactions without deeper modeling. |
| overlap recognised | `yes` | High collinearity between pairs (X1/X16, X3/X18, X2/X17) suggests that these pairs are functionally redundant—each pair represents a single underlying predictor. |
| proxy direction caveat | `yes` | High collinearity between certain features (e.g., X1/X16) makes it difficult to assign unique importance to individual features within each pair; we can only say that the shared signal is predictive. |
| p from r and n | `no` | With Bonferroni adjustment (α ≈ 0.0025 for 20 tests), the above variables remained significant. |
| numerical plausibility | `implausible` | Reports 'p < 1e-10' for X1 and X3 and 'p ~ 0.01' for X2 with no derivation, alongside an invented R^2 ~ 0.60. |
| unsupported computation | `many` | Unstandardised coefficients (2.3, -1.8, 0.15) with p < 1e-10, an invented R^2 ~ 0.60, and claims of residual plots, added-variable plots and model comparisons. |

Linear features claimed supported: `['X1', 'X3', 'X2']` | any term supported: `yes` | other second-order entries: `['X1*X3', 'X2*X3']`

