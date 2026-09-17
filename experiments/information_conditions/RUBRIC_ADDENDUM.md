# RUBRIC addendum — corrections that could not be made in the frozen file

`RUBRIC.md` is covered by the design hash and both freezes. It is left exactly as the papers were scored
against it. Errors found in it afterwards are recorded here instead, so the frozen text and the correction are
both on the record.

This file is **not** in `DESIGN_GLOBS` and does not affect either freeze.

## 1. The normality claim for Table 2 is not supported (added 2026-09-17)

`RUBRIC.md` section 5, under "Which test, and on which table", says the bivariate-normality assumption behind
the Pearson t-test is "reasonable for **Table 2** (Y against a second-order term)". **That is not justified.**
Table 2's entries are correlations of Y with squares `Xi²` and cross-products `Xi*Xj`. A square of a normal
variate is chi-square-distributed, not normal; a product of two independent normals is not normal either. The
marginals are skewed and heavy-tailed, so the pair is not bivariate normal, and the assumption does not hold any
better there than it does for Table 1 — which the same section correctly flags.

The rubric's Table 1 caveat was right; extending an endorsement to Table 2 was not.

**What this changes in practice:** nothing about how the 30 papers were scored, because
`numerical_plausibility_of_reported_calculations` was applied as an arithmetic check throughout — does the
number the paper prints follow from the r and n it was given, under the formula it used — and no paper's score
turned on whether the distributional assumption holds. The corrected statement of the field's meaning is:

> This field checks the **arithmetic of the formula the paper invokes**. It does not certify that the test's
> assumptions are satisfied. For a correlation involving a squared or cross-product term, or a squared residual,
> the normal-theory p-value should be read as a rough screening quantity, and a paper that says so is being more
> accurate than one that does not.

Anyone re-deriving significance from Table 2 for a future analysis should use a permutation or bootstrap
reference distribution rather than the normal-theory t-test.

## 2. Nothing else

No other correction to `RUBRIC.md` was identified during scoring or post-unmask verification.
