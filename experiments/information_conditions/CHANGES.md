# Changes and deviations log

Every entry records what was changed or decided, why, and the consequence for the experiment. Add an entry for any change made after a freeze; the runner refuses to execute a phase whose design hash differs from the latest freeze for that phase.

## Post-run defect summary

This file is the authoritative list of defects found after the formal run. `REPORT.md` names the same six
categories and they correspond one to one with the rows below. All six were found after 2026-09-15, none
affected the completed experiment, and none prompted a re-run or a rescoring.

| # | Category | What was wrong | Entry |
|---|---|---|---|
| 1 | Manifest reproducibility | Raw float64 from numpy linear algebra reached the design hash, so a rebuild on another machine drifted in the last digit and could invalidate a freeze with no input change. | 2026-09-17, item 1; second pass, item 1 |
| 2 | Review-pipeline validation | A missing form, a duplicated run record, and a silent replacement of an existing lock were all accepted. Duplicate-record protection is part of this category, not a separate one. | 2026-09-17, item 3 |
| 3 | Malformed-response handling | `{"choices": [42]}` and a string `message` raised an uncaught `AttributeError`, bypassing bounded retry and the failed record. | 2026-09-17, item 4 |
| 4 | Report validation | `tests/test_report.py` checked a row count modulo the template's and only two columns, so it could not tell that an outcome table had been dropped. | 2026-09-17, item 6 |
| 5 | Dataset preservation (branch defect) | `ensure_full_datasets` overwrote a dataset that was already on disk whenever the other one was missing. | third pass, item 1 |
| 6 | Resolved model identifier (branch defect) | Preflight checked the short model key but never the identifier it resolves to, which is set outside the design hash. | third pass, item 2 |

Two further corrections were not code defects and are recorded separately: three rounding verdicts in the
post-unmask numerical check (2026-09-17, item 2) and wording in `REPORT.md` and the PR description
(2026-09-17, item 5; second pass, item 2).

## 2026-09-15: initial design (pre-freeze)

1. **Full datasets regenerated, not read from the repository.** The task asked to reuse the committed live and dead CSVs. The upstream commits only 10-row samples (`datasets/*_sample.csv`); the 1000-row files that `prepare_summary` reads are gitignored. `infocond/data.py` regenerates them by calling the upstream generator functions in the exact draw order of its `main()` with the upstream seed 42, writes only the two gitignored files, and refuses to continue unless the first 11 lines are byte-identical to the committed samples and the correlations with Y and the OLS R² equal the committed `results/baseline_*.json` values. No seed was chosen; no committed file was touched. Hashes of the regenerated files, the committed samples, the generator, and `ground_truth.json` are in `inputs/manifest.json`.
2. **Model choice.** `openai/gpt-4.1` (upstream key `gpt-4.1`) is used, taken verbatim from `src/run_ai_scientists.py`. Reasons: first-listed upstream model, non-preview identifier, and the largest upstream coefficient error. The earlier wording ("weakest upstream detection") overstated the evidence and is withdrawn: `results/summary_table.csv` shows `Interaction=False` for all nine upstream live runs, so on the outcome this experiment measures the three models are tied at 0/3, and gpt-4.1's mean TPR equals claude-sonnet-4.5's. `run --model` can preview another upstream identifier in a **dry run only**; `--execute` refuses anything other than the `config.json` value. This choice is a design decision, not a result.
3. **Sample verification method.** An initial implementation compared `df.head(10).to_csv()` after reading the regenerated CSV back through pandas; that failed because the default C float parser does not round-trip the last digit of `repr`. Replaced with a text-level comparison of the first 11 lines of the file against the committed sample. The data were identical in both cases; only the check changed.
4. **Forbidden-content check.** The first version used bare substrings such as `2*x1`, which falsely matched the legitimate condition-B row `X12*X13`. Replaced with anchored regular expressions for the true formula fragments plus plain substrings for dataset identities and answer-key vocabulary. Self-tests cover both the true positives and the false positive.
5. **Term naming and order.** Squares are written `Xi^2` and cross products `Xi*Xj` with i<j, so the proxy term the task calls "X19 * X5" appears in Table 2 as `X5*X19`. The rubric and review form treat the two spellings as one term.
6. **Token estimate.** The common chars/4 rule underestimates numeric tables badly. The committed upstream records give the provider's `prompt_tokens` for the condition-A prompt (about 10.5k characters): 5,518 for gpt-4.1, 5,481 for claude-sonnet-4.5 and 7,226 for gemini-2.5-pro, i.e. 1.90, 1.91 and 1.45 chars/token. A first draft used 1.8, which is not conservative for the Gemini tokenizer; changed to 1.4 (below all three) with a 60,000-token ceiling. The calibration is recorded in the manifest. This is an estimate, not a tokenizer.
7. **max_tokens kept at the upstream 4096.** Condition B is longer and may produce longer papers; truncation is flagged per record and counted separately rather than trimmed or retried. Raising the limit would be a design change requiring a new freeze and a note here.
8. **Empty response treated as a technical failure.** A 200 response whose message content is missing or whitespace-only is retried like a malformed response. This is a structural check; the text of a non-empty paper is never inspected for retry decisions.
9. **Git identity.** `user.name` and `user.email` are unset locally and globally in this environment and were not changed. The branch `experiment/information-conditions` was created from the baseline commit and only this task's files were staged; `git commit` failed with `fatal: unable to auto-detect email address (got '<redacted-host>')`. The repository owner completes the initial-design commit from the checkout with their own identity, for example `git -c user.name="<name>" -c user.email="<email>" commit -m "Add information-conditions experiment design"` (the staged tree is the intended commit content). No smoke call may be made before that commit and a `freeze --phase smoke`.
10. **Stray file.** An aborted shell command during implementation left an untracked draft `cli.py` at the repository root; it was deleted before staging. Nothing outside `experiments/information_conditions/` is added or modified.

## 2026-09-15: independent review fixes (still pre-freeze, pre-smoke)

An independent review of the design found no blocking defect but five important ones and several minor ones. All were fixed in one pass before any call was made; no result exists that these changes could affect.

11. **Manifest split into design record and environment record.** `inputs/manifest.json` embedded `git.head_commit`, `git.working_tree_dirty`, `git.branch`, `git.origin_url`, `datasets.*.regenerated_now` and `package_versions.platform`, and is part of the design hash. Three consequences: re-running `generate-inputs` after committing invalidated the freeze even though all six prompts were byte-identical; on a fresh clone `regenerated_now` flipped to `true`, so nobody else could reproduce the committed manifest; and the committed manifest recorded the tree state *before* the commit containing it, so its own provenance was wrong. The manifest now holds only design content and reproduces byte for byte on any machine. The environment record moved to `inputs/provenance.json`, which is outside the design hash. The versions that genuinely affect generation were **not** dropped: `config.json::environment` declares `python_minor`, `numpy` and `pandas`, `generate-inputs` warns on a mismatch and `run --execute` refuses.
12. **`cli.py` added to the design hash; report structure frozen separately.** `DESIGN_GLOBS` covered `infocond/*.py` but not `cli.py`, which decides when `--execute` runs, which model key is used and how the review is exported — a post-freeze change to it was invisible. `REPORT.md` was deliberately *not* added: freezing the filled report would make writing up results look like a design change. Instead the structure lives in the new `report_template.md` (sections, the six rows per outcome table, column definitions, required scope statements), which is frozen; `REPORT.md` is the working copy and a test checks it still conforms to the template.
13. **`--model` can no longer bypass the freeze.** `execution_preflight` compared the manifest's model key against `config.json` but never against the model the run would actually call, so `run --execute --model <other>` passed preflight and would have made paid calls with a model neither the freeze nor the manifest described. Preflight now receives the effective model key and refuses a mismatch. The flag remains for previewing a dry-run schedule.
14. **A preview can no longer overwrite an executed schedule.** `run_phase` rewrote `runs/<phase>/schedule.json` unconditionally, so a later dry run — especially with `--model` — silently replaced the record of what was executed. The schedule is now written only when absent or unchanged; if it differs and the phase already has records or a `summary.json`, the run refuses.
15. **Review export is driven by the schedule, not by the records directory.** `collect_success_records` globbed every `*.json` under `records/`. Because the cache key is part of the filename, a prompt or request-setting change mid-phase leaves the old records in place, and they would have been exported and scored alongside the new ones, double-counting those cells. Export now takes only records whose `cache_key` appears in `runs/<phase>/schedule.json` and reports the rest as off-plan, on stderr and in `EXPORT_INFO.json`. `schedule.json` is required; export refuses without it.
16. **Record writes are atomic.** `write_json` wrote in place, so an interruption left an unparseable record that aborted every later run of that phase (loudly, but unrecoverably through `--retry-failed`). Writes now go to a sibling `.tmp` file, are fsynced, and are renamed into place. Paper and prompt text use the same path.
17. **Rubric: the test behind `numerical_plausibility_of_reported_calculations` is now stated.** The rubric named `t = r·sqrt((n−2)/(1−r²))` and the |r| > 0.062 boundary at n = 1000 but attached no assumptions. Table 1 correlates squared residuals with squared predictors — both non-negative and right-skewed, with e a fitted residual — so normal-theory p-values are not valid there. Reviewers are now told to score the arithmetic, record the test used, and not treat the distributional assumption as met for Table 1; a paper that notes the problem is credited, not penalised.
18. **`unmasked_summary.csv` now carries what `REPORT.md` says it carries.** It was missing the contradiction flags, the other second-order terms and every auxiliary field, although `REPORT.md` promised auxiliary summaries from that file and has a "Contradictory statements" column. 31 columns now.
19. **Extraction aid: product notation separated from co-mention; form spelling used.** `X4 and X5` was reported under the same key as `X4*X5`, and `second_order_terms_mentioned` emitted the numerically sorted `X5*X19` while the form and rubric use `X19*X5`. Pointer output only; no score depended on either.
20. **Environment pinned in the README.** `uv.lock` forks on the interpreter (Python 3.10 → pandas 2.3.3 / numpy 2.2.6; ≥ 3.11 → pandas 3.0.1 / numpy 2.4.3) and `pyproject.toml` allows `>=3.10`, so `uv sync --frozen` alone was not reproducible. The README now pins `--python 3.13` and explains why pytest is installed separately. `pyproject.toml` and `uv.lock` are upstream files and were not modified.

21. **Explicit refusals are a third terminal outcome, not a malformed response.** `parse_success_body` validated `message.content` before anything else, so a structured refusal — which normally arrives as `refusal: "..."` with `content: null` — looked like "content missing or not a string" and was retried three times as a technical failure, then stored as `status: "failed"` with the refusal text discarded. The refusal check now runs before content validation: a non-empty `message.refusal`, or a content-filter finish reason (`content_filter`; native `refusal`, `SAFETY`, `PROHIBITED_CONTENT`, `BLOCKLIST`, `IMAGE_SAFETY`, `SPII`), raises a terminal `ContentRefusal`. The record gets `status: "refused"` with the raw response, refusal text, refusal reason, finish reasons and usage preserved, and exactly one attempt. It is never retried — neither by the backoff loop nor by `--retry-failed` — because re-rolling a refusal is replacement sampling on content, which the design forbids everywhere else. Refusals are counted in their own `refused` / `already_cached_refused` fields and enumerated in `summary.json::refusals`; `export-review` keeps them out of the papers given to reviewers and reports the count; `REPORT.md` and `report_template.md` gained a `Refused` column so they are reported alongside failures and truncations rather than silently reducing the completed count. Genuinely malformed responses (content missing, null content with no refusal field, whitespace only, no choices) keep their bounded retries. No prompt changed and no call was made.

Two review questions were resolved as **not** defects and no change was made:

- **The token factor 1.8 → 1.4 is correct as it stands.** The estimate is `ceil(chars / factor)`, so a smaller factor yields *more* estimated tokens and is the conservative direction. 1.4 sits below the smallest ratio implied by the upstream records (1.449 for gemini-2.5-pro), so it errs high for every upstream model including the selected one. What the ceiling of 60,000 means for `openai/gpt-4.1` specifically is still an external fact, recorded as such; condition B estimates 12,895 tokens.
- **The dataset documentation does not overclaim.** `README.md`, this file and `infocond/data.py` all scope the claim to "first 11 lines byte-identical to the committed samples" plus "correlations and OLS R² equal to the committed baselines". Full byte identity of rows 11–1000 with whatever upstream ran is not claimed and cannot be established, because the upstream commit never contained those files.

## 2026-09-16: scoring of P009fd2 (first paper)

Human scoring of the formal export began. `review/formal/export_20260915T144035Z/forms/P009fd2.json` is filled
and passes schema validation; all ten recorded quotes were checked byte-for-byte against the paper. No other form
was touched, and `lock-reviews` / `unmask` have not been run.

Method, recorded for the record: Claude Opus 5 drafted a recommendation for each field from `RUBRIC.md`,
`review_schema.json` and the paper text only, and Evelyn Gao confirmed or overrode each field one at a time
before it was written. One field was overridden: `model_misspecification` was recorded as `proposed` rather than
the drafted `rejected`. The original AI draft is preserved unchanged at
`review/formal/export_20260915T144035Z/ai_draft/P009fd2.draft.json` so the two can be compared.

**The AI assistance for this paper was not blind.** Earlier in the same session, while measuring how often paper
text leaks its dataset label, the dataset and condition of the 13 label-quoting papers were printed, and P009fd2
was among them. The field-by-field reasoning was written from the paper text alone and no mapping, run record or
input file was read during scoring, but Claude cannot be said to have been unaware of this paper's identity. By
the reviewer's decision this is recorded here and in `ai_draft/P009fd2.rationale.md` rather than inside the form.
Consider an independent re-score of P009fd2 before using it as a calibration reference.

Two numeric checks were performed offline and are recorded in the form: r = 0.08 at n = 1000 gives t = 2.535 and
p = 0.0114 (Pearson t-test, df = 998, two-sided), and the nominal / Bonferroni(20) boundaries at n = 1000 are
|r| > 0.0620 and |r| > 0.0955. Values that require the supplied input are listed in the form's `overall_notes`
as deferred to post-unmask verification.

## 2026-09-16: scoring process changed from human to AI for the remaining 29 papers

This is a change to the **scoring** process made after the formal run, not to the frozen design. No prompt,
rubric, schema, config or freeze file was touched, and both freezes still verify.

**What changed and why.** Scoring P009fd2 field by field with human confirmation took about two hours. At that
rate the remaining 29 papers were not viable, so the reviewer directed that Claude score them and that the human
role be reduced to a spot-check. Recorded here because it changes the evidential status of 29 of the 30 forms.

**Status of the forms, honestly stated:**

- `forms/P009fd2.json` -- drafted by Claude, **confirmed field by field by Evelyn Gao**. `reviewer` reads
  "Evelyn Gao". One field (`model_misspecification`) was overridden by the human from `rejected` to `proposed`.
- The other 29 forms -- **scored by Claude (claude-opus-5[1m]) on 2026-09-16, not human-verified.** `reviewer`
  reads "Claude (AI-scored, not human-verified)" on every one of them, and each `overall_notes` repeats that
  status. **The human spot-check has not been done yet.**

**Not a strictly blind score.** Earlier in this session, while measuring how often paper text leaks its dataset
label, the dataset and condition of the 13 label-quoting papers were printed. Claude therefore already knew the
identity of a subset of this export before scoring it. Scoring was done from the paper text alone and no mapping
file, run record or supplied input file was opened during it, but the blinding claim cannot be made.

**Precedents applied**, all inherited from the human-confirmed P009fd2 and applied uniformly: an unnamed blanket
rejection of interaction effects scores `rejected` for the exact target and all three proxy targets; the four
interaction targets are judged from the same sentence unless the paper names a specific product, in which case
the named quote is used; corr(e^2, Xi^2) mentions belong to `heteroscedasticity` and not to
`other_second_order_terms`, while second-order terms named in prose as correlates of Y do get an entry; and a
Limitations hedge that the supplied statistics cannot rule out more complex structure scores
`model_misspecification: proposed`. No unconfirmed reclassification was introduced.

**Verification performed:** all 30 forms pass `review.validate_form` against the frozen schema, and all 380
recorded quotes were checked to be byte-exact substrings of their paper. Numeric claims were checked offline only
where they are derivations from r and n (four papers report an r-threshold or p that could be verified: P4cc9fc,
Padefb8, Pc14d00, Pf0b1ac -- all correct). Every value that would need the supplied input file to confirm is
marked PROVISIONAL in the form and listed under DEFERRED TO POST-UNMASK.

**Artifacts added:** `review/formal/export_20260915T144035Z/AI_SCORING_CHECKLIST.md` (one line per paper with the
main conclusion and the judgement calls) and `SPOTCHECK.md` (key fields and evidence for the three sampled
papers). The three were drawn with `random.Random('P009fd2-spotcheck-20260916').sample(sorted(ids), 3)` over the
29 AI-scored ids, which reproduces P1f4ee0, P47d32e and Pdb7d7c.

**Consequence for the report.** Any result computed from these forms rests on AI scoring that a human has not
checked. `REPORT.md` must say so when it is written, and the spot-check should be completed first.

## 2026-09-17: spot-check, lock, unmask, verification, report

**Human spot-check, actual scope.** Evelyn Gao spot-checked the 3 papers drawn on 2026-09-16 (P1f4ee0, P47d32e,
Pdb7d7c), examining the 9 fields listed in `SPOTCHECK.md` and retaining the AI value for every one of them without
modification. Those three forms now carry `reviewer: "Claude (AI-scored); human spot-check by Evelyn Gao 2026-09-17
on 9 of 22 fields, all retained"`, and their `overall_notes` names the 9 fields and states that the other 13 were
not examined. **The remaining 26 forms are unchanged and still read "Claude (AI-scored, not human-verified)".**
Nothing was marked human-verified that a human did not look at.

**Lock and unmask.** `lock-reviews` was run after the spot-check marks were written, then `unmask` against
`mapping_20260915T144035Z.json`. `verify_lock` still returns OK after unmasking, so no form was touched in
between. Outputs: `unmasked_reviews.json` and a 31-column `unmasked_summary.csv`.

**Post-unmask verification of the PROVISIONAL numbers.** Recorded in
`review/formal/export_20260915T144035Z/VERIFICATION_POST_UNMASK.md`. **No score was changed.** Every supplied
value quoted by a paper matched `inputs/` exactly; the four derivations from r and n recompute correctly; every
paper that cited material its condition never supplied had already been caught by the blind scoring. Two
observations were recorded without changing a field: P235541 and P352adf name X4*X5 and X19*X20 as the two largest
second-order terms and skip X5*X19, which is larger than X19*X20 (incomplete enumeration, not a wrong number); and
Pc360e8 mentions R² only in the conditional, so its `unsupported computation: none` stands. The verification file
carries an empty corrections table with the columns an amendment would use, so any future correction is recorded
rather than applied silently over the lock.

**Report.** `REPORT.md` filled from `unmasked_summary.csv` with per-cell counts as k/5, plus two breakout tables
the template does not have (heteroscedasticity alone, and the auxiliary fields). `tests/test_report.py` required
the report's combination rows to equal the template's exactly; it was relaxed to require the template's rows to be
a prefix and every 6-row block to carry the same six combinations, with the reason written into the docstring.
`tests/` is not in `DESIGN_GLOBS`, so this does not touch either freeze; both still verify.

**Headline result.** `exact_interaction_X4_X5` is `rejected` in 30/30 papers, 0/5 supported in every cell,
including the five live condition-B papers handed a table in which X4*X5 is the largest second-order correlate.

## 2026-09-17: external review fixes (code, verification and report; no re-run)

An external reviewer ran the suite at `c88a910f` on Python 3.13 / NumPy 2.4.3 / pandas 3.0.1 and got 79 passed,
1 failed, without touching the original files or calling the API. All five findings were reproduced or accepted
and fixed. **No experiment was re-run and no locked score was rewritten.**

1. **Manifest was not byte-reproducible across machines.** The reviewer's rebuild matched on all six prompt
   hashes but differed in 443 float values in the last digit (example: `-0.028491680456637882` vs
   `...872`), and those unrounded float64 results from numpy linear algebra were inside the design hash, so
   another machine could see a valid freeze go invalid with no input change. Their failing test was
   `test_committed_manifest_matches_a_fresh_build`. **This did not reproduce on the original machine (0 diffs,
   test passing), so the fix rests on their reproduction, not mine** — but unrounded linear-algebra output has no
   business in a content hash either way. `infocond/manifest.py` now carries
   `manifest_format_version = 2` and rounds every float in the record to 12 decimals (`normalise_floats`, which
   also folds `-0.0` to `0.0`). The "byte for byte on any machine" promise in the module docstring is replaced by
   a precise one. **The committed 2026-09-15 manifest and both freezes are format v1 and are deliberately left
   untouched**, because the formal run was executed under them; regenerating them would misrepresent what was
   frozen. `test_committed_manifest_matches_a_fresh_build` therefore compares the legacy record numerically with a
   1e-9 tolerance and exactly on everything else, and two new tests pin v2 normalisation.

2. **Three rounding verdicts in the post-unmask check were wrong.** The reviewer recomputed independently:
   P4cc9fc's "r = .059 → p = .07" is 0.062176 and rounds to .06; Padefb8's Bonferroni boundary "≈ .11" over 230
   tests is 0.116684 and rounds to .12; Pf0b1ac's ".00024" is 0.05/230 = 0.00021739 ≈ .00022, and .00024 instead
   matches a 210 denominator the same paragraph contradicts. My earlier "all four correct at stated precision"
   was wrong — the comparison had been made too loosely. All three are now recorded in the corrections table in
   `VERIFICATION_POST_UNMASK.md` with original value, new value, basis and effect, and
   `numerical_plausibility_of_reported_calculations` moves `plausible` → `implausible` for those three.
   **The locked forms keep their original values**; `REPORT.md` shows locked and corrected counts side by side.
   Only dead_salmon/A and dead_salmon/B move, and no primary count changes.

3. **Scoring pipeline would accept a missing form and a duplicated record.** Reproduced by the reviewer in a
   temporary copy: deleting a form still locked and unmasked cleanly with 29 papers; duplicating a run record
   exported 31; and editing a score after unmasking and re-running `lock-reviews` silently replaced the lock and
   re-verified. `infocond/review.py` now raises when two records claim one scheduled `cache_key`, when the paper
   and form id sets disagree (checked at export, at lock and at unmask), and when an existing `LOCK.json` would
   be replaced by a different one — re-locking identical content stays a no-op, and a genuine pre-unmask
   correction needs `--relock-note`, which is preserved in `superseded_locks`. Four regression tests added.
   **The actual data had neither a gap nor a duplicate**; this closed a process hole, it did not repair a result.

4. **Some malformed responses crashed the run instead of being retried.** `{"choices": [42]}` and
   `{"choices": [{"message": "oops"}]}` raised an uncaught `AttributeError` out of `parse_success_body`, so the
   call never reached the bounded-retry path and no failed record was written. Reproduced locally. Type checks
   added for `choices[0]` and `message`; both now classify as transient and exhaust the normal three attempts.
   Regression test parametrised over four shapes. None of the 30 formal responses hit this.

5. **Report and PR description corrected.** "Four of those five named X4\*X5" was wrong — I re-read all five
   live-B papers and **all five** name it and quote its correlation, with differing stated reasons (two cite
   absent marginal effects, three cite collinearity); both documents now say five and give the reasons
   separately. The 30/30 figure now carries the scoring convention explicitly: a blanket rejection of all
   interactions is scored `rejected` for the exact target under RUBRIC section 6, so 30/30 does not mean 30
   papers each examined X4·X5 by name. The claim that "the uniform 30/30 rejection is the only result the sample
   size supports firmly" is removed — the six cells differ in condition and in whether the data contain signal
   and cannot be pooled. "Supplying the answer in tabular form" is restated as "supplying the second-order
   correlation statistics did not produce a supporting claim". The Design section no longer says "Scoring: human
   review".

6. **Two smaller items.** `tests/test_report.py` had been relaxed on 2026-09-17 in a way that only checked a row
   count modulo the template's and only the dataset and condition columns; it is rewritten to check each outcome
   table separately — every table must carry all six combinations exactly once, and every header the template
   defines must still appear in the report with identical columns. And `RUBRIC.md` section 5 asserts that
   bivariate normality is "reasonable for Table 2"; it is not, since squares and cross-products of normals are
   not normal. `RUBRIC.md` is frozen and is left exactly as scored against; the correction is in the new
   `RUBRIC_ADDENDUM.md`, which is outside `DESIGN_GLOBS`. No score turned on the assumption, because the field
   was applied as an arithmetic check throughout.

**Freeze status after these fixes — stated plainly.** Fixes 1, 3 and 4 changed `infocond/manifest.py`,
`infocond/review.py`, `infocond/runner.py` and `cli.py`, all of which are inside `DESIGN_GLOBS`. Both freezes
therefore now report NOT READY, naming exactly those four files. **That is the mechanism working, not a
regression**: the code that would execute a run is no longer the code the run was executed under.

Nothing historical was altered to make the status look better. The freeze files themselves, `inputs/`, all 30
run records and the review lock are byte-unchanged, and every run record still carries the design hash
`1940cf566a9c8f41` it was executed under. The 2026-09-15 formal results remain attributable to that frozen
design; they are not re-attributed to the fixed code.

**No new freeze was created.** Creating one now would produce a freeze that no run was executed under, which
invites exactly the misreading this workflow exists to prevent. Any future execution — a replication, another
model, another dataset — must create its own freeze first, and will then correctly record the post-fix design.

Test suite: 90 passed (was 80; 10 regression tests added).

## 2026-09-17 (second pass): version-aware manifest test and final wording

A second external review confirmed the earlier fixes on Linux (90 passed) and found one remaining code problem
and three documentation leftovers.

1. **The manifest test broke once a v2 record existed.** `tests/test_manifest.py` always stripped
   `manifest_format_version` from the fresh build, so it could only ever compare against a v1 file. Running
   `generate-inputs` as the PR instructs makes the committed file v2, and the test then reported
   `.manifest_format_version: present in only one` and failed — the fix for finding 1 had made its own test
   unusable. The comparison is now version-aware: it reads the version off the file, compares a v1 record
   numerically with a 1e-9 tolerance (stripping the key the v1 file does not have), and compares a v2 record
   strictly with the key kept. `test_comparison_is_strict_for_v2_and_tolerant_for_v1` pins all three paths,
   including that v2 must *not* tolerate the drift v1 does. Verified end to end in a temporary copy: after
   `generate-inputs` writes v2 the full suite is 91 passed, the six prompt hashes are unchanged, and a second
   `generate-inputs` reproduces the manifest byte for byte.

2. **Three documentation leftovers corrected.** `PR_DESCRIPTION.md` still described the manifest as
   "machine-independent and reproduces byte for byte" with no qualification; it now states the v2 rounding, the
   environment condition it holds under, and that the committed record is deliberately left at v1. `REPORT.md`
   still said post-unmask verification "changed no score", which contradicts the three corrections; it now says
   the locked forms were not modified and three auxiliary scores were revised through the corrections record.
   And two overstatements are gone: "the closest anything came to the mechanism" is replaced by the literal
   finding — those papers identified residual structure in X4/X5/X19/X20 and none connected it to a product term —
   and "invented output fell as real statistics rose" / "reduced how much it made up" is replaced by the scored
   statement, that fewer papers were scored as reporting unsupported numbers or claims of computation, with the
   caveat that this is an association across three conditions of five papers each and not a demonstrated
   mechanism.

Nothing else changed. No experiment re-run, no score rewritten, no new freeze. The committed v1 manifest,
`inputs/`, both freeze files, all 30 run records and the review lock remain byte-unchanged; both freezes still
correctly report NOT READY against the fixed code. Test suite: 91 passed.

## 2026-09-17 (third pass): two branch defects found in re-review

A third external review confirmed the suite at 91 passed both before and after generating a v2 manifest, and
found two defects on branches the earlier passes had not exercised. Both reproduced locally. Neither affects the
completed experiment: the datasets were present throughout, and all 36 records (6 smoke, 30 formal) requested and
received `openai/gpt-4.1`.

1. **`ensure_full_datasets` overwrote a present dataset when the other one was missing.**
   `regenerate_in_memory()` necessarily returns both frames — the two datasets share one RNG stream and the dead
   target can only be drawn after the live one — but the write guard was `if name in frames`, which is true for
   both as soon as either file is absent. Reproduced: with the live CSV present and the dead CSV missing, the
   live file was rewritten, contradicting the docstring's "existing files are left as is" and, worse, destroying
   whatever was on disk before `verify_datasets` could compare it against the committed samples and baselines —
   exactly the difference that check exists to surface. The guard is now `if name in missing`. Two tests added:
   one-present-one-missing preserves the present file byte for byte and creates only the absent one; both-missing
   writes both and a second call writes neither (mtimes unchanged).

2. **`execution_preflight` checked the short model key but never the resolved model id.** The key is resolved
   through `src/run_ai_scientists.py::MODELS`, which lives outside `experiments/information_conditions/` and is
   therefore outside `DESIGN_GLOBS`. If upstream remapped `gpt-4.1` to another identifier, every key-level check
   still passed while the run would have called a different model. Reproduced with a stubbed mapping and no API
   request: preflight passed and `make_plans` resolved to `openai/gpt-4o-mini` while the manifest froze
   `openai/gpt-4.1`. Preflight now resolves the key and compares it against `manifest["model"]["id"]`, refusing on
   mismatch and also refusing if the key has disappeared from the upstream table. Test added covering the
   baseline, the remap and the missing-key case.

Both regression tests were checked against the pre-fix code and fail there, so they pin the behaviour rather than
merely describing it. Test suite: 94 passed. No experiment re-run, no score rewritten, no new freeze; the
committed v1 manifest, `inputs/`, both freeze files, all 36 run records and the review lock remain byte-unchanged.

## 2026-09-17 (fourth pass): report rewritten around the multiple-comparison finding

A reviewer rewrote `REPORT.md` to state the multiple-comparison result explicitly and flagged three problems in
the draft. Numbers were re-verified against `unmasked_summary.csv` before the rewrite was accepted; every
auxiliary count and every row of the corrections table matched.

1. **Paper IDs collided between two quote blocks.** The draft cited P352adf and P83cd07 both among the five
   live-data B papers and among the three papers illustrating A_prime residual-diagnostic language. A paper
   belongs to one cell, and the random IDs are unique across the 30. Checked against the unmasked summary:
   P352adf and P83cd07 are live-data **B** papers, so the A_prime block was mislabelled and did not show the
   three A_prime papers it was meant to illustrate. Replaced with the three live-data A_prime papers that
   actually proposed or supported heteroscedasticity: Pa59545, Pe68172 and Pf92ce7. Their quotes were taken from
   their own forms and verified against their own paper text.

2. **The reason split did not match the quotes.** P83cd07 gives both absent marginal associations and
   collinearity in one sentence, so a two-versus-three split of papers was not reconcilable with the quotes a
   reader can see. The report now states the reasons as non-exclusive: absent marginal associations in P235541,
   P352adf and P83cd07; collinearity in P54ad99, P83cd07 and P8ba206; P83cd07 giving both.

3. **The defect list differed between versions.** An earlier report listed duplicate-record protection as its own
   category and a later one dropped it. This file now opens with an authoritative defect summary of six numbered
   categories, `REPORT.md` names the same six and says this file is authoritative, and duplicate-record
   protection is stated there as part of review-pipeline validation rather than as a separate item.

Two quotes also failed a byte-exact check against their source and were corrected: P83cd07's began with a
capitalised "These" where the paper reads "but these", and Pe68172's used a straight apostrophe where the paper
has a typographic one. All eight quotes in the report are now verbatim substrings of their papers, no ID appears
in two blocks, and each cited paper's cell matches the unmasked summary.

No score, input, run record or freeze was touched. Test suite: 94 passed, including the report structure check.

Before publication, machine-specific strings were redacted in the published copy: the hostname in the quoted git error in the initial-design entry above (`<redacted-host>`), and the absolute home-directory prefix in `review/formal/export_20260915T144035Z/EXPORT_INFO.json` (`mapping_location`) and `review/formal/mapping/mapping_20260915T144035Z.json` (`export_dir`) (`<redacted>`). Neither file is covered by `LOCK.json`, `INTEGRITY.md` or the design hash, so no freeze or lock is affected.

## Post-smoke changes

**Smoke phase executed 2026-09-15 under freeze `smoke_20260915T140534Z.json` (design hash `1940cf566a9c8f41`, git head `73b4657`, clean tree). No change was required, so the design hash is unchanged and the formal freeze records the same design the smoke calls ran under.**

Outcome: 6 planned, 6 called, 6 success, 0 refused, 0 failed, 0 truncated, 0 model mismatch; one attempt each, so the retry path never fired. Requested `openai/gpt-4.1` and returned `openai/gpt-4.1` from provider `OpenAI` on every call, `finish_reason: stop`, `native_finish_reason: completed`, `refusal: null`. Cost $0.120662 total (`is_byok: false`); the rates implied by `cost_details` are $2.00/M input, $0.50/M cached input and $8.00/M output, and four of six calls reused a 4,992-token cached prefix, which is what makes per-call cost vary between similar-sized requests.

Two things the smoke phase settled that no offline check could:

- **The input-length estimate is conservative on the selected model.** Estimated tokens ran 1.34x-1.45x above the provider's `prompt_tokens` in every cell, never below. Largest real input 9,612 tokens against the 60,000 ceiling, and the longest completion was 1,859 of `max_tokens` 4,096, so there was no truncation pressure. The `chars_per_token_conservative = 1.4` value chosen in entry 6 is now validated against `openai/gpt-4.1` itself rather than inferred from another provider's ratio.
- **Condition A tokenizes to exactly 5,518 `prompt_tokens`, identical to the committed upstream record `results/papers/live_salmon_gpt-4.1_run1.json`.** This is the first corroboration of the condition-A equality claim that does not come from re-running `prepare_summary` itself. It is not proof of byte identity -- different strings can share a token count -- but a drift in the regenerated data or in the pandas rendering would very likely have changed it.

Smoke papers are excluded from `REPORT.md` by design and were not read for their claims; only structure and scorability were checked (all six carry Title/Abstract/Methods/Results/Discussion/Limitations, end cleanly, 743-1,092 words, and 112 of 113 reported numbers trace back to the supplied input).

Formal freeze created immediately after this entry was committed. Any change made from here on requires a further entry and a further freeze before `run --phase formal --execute`.
