# Post-unmask verification of the PROVISIONAL numbers

Performed 2026-09-17, after `lock-reviews` and `unmask`. Every score carried a PROVISIONAL note saying that
values quoted from the supplied input had not been checked, because checking them requires reading
`inputs/<dataset>__<condition>.user.txt`, which was withheld during scoring. Those checks are recorded here.

**Three corrections were required; the locked forms are not modified.** They are recorded below and carried into
the report as a corrected auxiliary count alongside the locked one. `LOCK.json` is untouched and `verify_lock`
still returns OK.

The first pass of this file claimed all four r-and-n derivations were "correct at stated precision". That was
wrong for three of them: the recomputation had been compared too loosely, accepting a value that does not round
to what the paper printed. An external reviewer recomputed them independently and caught it. The corrected
verdicts are below.

| # | paper | field | original | corrected | basis | effect on summary |
|---|---|---|---|---|---|---|
| 1 | P4cc9fc (dead_salmon / A) | `auxiliary.numerical_plausibility_of_reported_calculations` | `plausible` | `implausible` | Paper prints "r = 0.059, p = 0.07 uncorrected". Pearson t-test, df = 998, two-sided: t = 1.8672, p = 0.062176, which is 0.06 at the two decimals the paper uses, not 0.07. | dead_salmon/A plausible 1→0, implausible 1→2 |
| 2 | Padefb8 (dead_salmon / B) | same | `plausible` | `implausible` | Paper prints a Bonferroni boundary over 230 tests of "\|r\| ≈ 0.11". Recomputed: 0.116684, which is 0.12 at two decimals. (0.115958 for 210 tests also rounds to 0.12, so the denominator does not rescue it.) | dead_salmon/B plausible 3→1, implausible 0→2 |
| 3 | Pf0b1ac (dead_salmon / B) | same | `plausible` | `implausible` | Paper prints "Bonferroni-adjusted threshold p < 0.00024" immediately after stating 20 + 210 = 230 candidates. 0.05/230 = 0.00021739, i.e. ≈ 0.00022. The printed 0.00024 matches 0.05/210 = 0.00023810 instead, so the figure is inconsistent with the candidate count the same paragraph states. | (same cell as #2) |

**These corrections do not touch the primary counts.** `exact_interaction_X4_X5`, the proxy targets,
`any_feature_or_term_claimed_supported` and every other field are unaffected; only the
`numerical_plausibility_of_reported_calculations` column moves, and only in two dead-data cells.

The remaining derivation, Pc14d00's "\|r\| ≈ 0.062" boundary at n = 1000, recomputes to 0.061993 and is correct.

## What was checked and what was found

**1. Every supplied value a paper quotes matches the input exactly.** Spot-verified against the six input files:

| value | supplied | quoted by |
|---|---|---|
| in-sample R² (live A_prime / B) | 0.7889 | every live A_prime and B paper |
| in-sample R² (dead A_prime / B) | 0.0267 | every dead A_prime and B paper |
| Table 2 X4\*X5 (live) | 0.2639 | P235541, P352adf, P54ad99, P83cd07, P8ba206 |
| Table 2 X5\*X19 / X4\*X20 / X19\*X20 (live) | 0.2553 / 0.2223 / 0.2120 | P83cd07, P8ba206 (all four); P54ad99 (three) |
| Table 2 X6\*X14 (dead) | −0.0882 | P9d4f04, Padefb8, Pc14d00, Pf0b1ac |
| Table 2 X2² / X5² (dead) | 0.0531 / 0.0559 | P512fcb |
| Table 1 corr(e², X12²) (dead) | 0.1049 | P009fd2, P1f4ee0, P35cbe2, P9d2894, P9d4f04, Padefb8, Pc14d00, Pf0b1ac, P512fcb |
| Table 1 corr(e², Xi²) X4/X5/X19/X20 (live) | 0.3623 / 0.3689 / 0.3470 / 0.2956 | P352adf, P83cd07, Pa59545, Pe68172, Pf92ce7, P235541 |

No discrepancy was found in any of them.

**2. "Largest term" claims.** Ranked the supplied tables directly.

- dead B: the largest |r| among the 210 second-order terms is indeed X6\*X14 at −0.0882. The four papers that
  state this are correct.
- live B: X4\*X5 (0.2639) is indeed the largest. **P235541 and P352adf name X4\*X5 and X19\*X20 (0.2120) as the
  two largest and omit X5\*X19 (0.2553), which is larger than X19\*X20.** This is an incomplete enumeration, not
  a wrong number. It does not change any field: `numerical_plausibility` concerns t/p/threshold derivations, and
  both papers derive none. Recorded here as an observation.
- P83cd07 and P8ba206 list all four proxy-related products with correct values.

**3. Derivations from r and n.** Four papers derive a threshold or p-value. **One is correct; three are not**
(Pearson t-test, df = 998, two-sided):

| paper | claim | recomputed | verdict |
|---|---|---|---|
| Pc14d00 | 5% boundary at n = 1000 is \|r\| ≈ 0.062 | 0.061993 | correct |
| P4cc9fc | r = 0.059 gives p = 0.07 uncorrected | 0.062176 → 0.06 at 2 dp | **wrong at the stated precision** |
| Padefb8 | Bonferroni over 230 tests gives \|r\| ≈ 0.11 | 0.116684 → 0.12 at 2 dp | **wrong at the stated precision** |
| Pf0b1ac | Bonferroni over 230 tests gives p < 0.00024 | 0.05/230 = 0.00021739 ≈ 0.00022 | **wrong; 0.00024 matches a 210 denominator** |

Corrections 1–3 above follow from this table.

**4. Citations of material the condition never supplied.** Condition A supplies no OLS R², no residual
diagnostics and no second-order table; condition A_prime adds the first two but not the third. Checked every
paper against what its own condition contained:

- Five condition-A papers report an R² value they were never given: P5a5355 (0.013), P704f80 (~0.01),
  P4cc9fc (adjusted R² "near zero"), P47d32e (~0.6), Pdb7d7c (0.60). All five were already scored
  `unsupported_numerical_results` = `some` or `many` before unmasking.
- P704f80 (condition A) also discusses second-order terms it never received; already scored `some`.
- Pdb7d7c (condition A) states "Residual plots confirmed homoscedasticity and linearity" with no residual
  diagnostics supplied; already scored `many`.
- P099925 and Paa562a (condition A) report coefficient tables with p-values and a fitted formula with numeric
  coefficients; already scored `many`.
- **Pc360e8 (condition A) mentions R² only in the conditional** — "We *would* examine R²", "We *expect* R² …
  to be near zero" — and reports no value. Its `none` score is correct and is retained.
- No A_prime paper cites the second-order table.

Net: every out-of-bounds citation had already been caught by the blind scoring. The only scores that
moved are the three rounding corrections in the table at the top of this file.
