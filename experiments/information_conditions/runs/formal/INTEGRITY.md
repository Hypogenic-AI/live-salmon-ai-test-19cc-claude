# Formal run integrity summary

Generated 2026-09-15T14:45:17+00:00 by inspecting `runs/formal/` after execution. No API call, no re-run, no scoring. Smoke is excluded throughout.

## Verdict

**Complete.** 30 planned, 30 called, 30 success, 0 refused, 0 technical failures, 0 truncated, 0 model mismatches. Every check below passed. One transient network error was retried once and succeeded; both attempts are preserved in the record. Nothing requires a re-run, and nothing was re-run for an unfavourable result.

## 1. Identity and plan conformance

| check | result |
|---|---|
| `schedule.json` planned calls | 30 |
| six dataset x condition cells, 5 reps each | PASS (reps 1-5 present in every cell) |
| cache keys unique | PASS (30 distinct) |
| record files | 30, one per planned call, 0 extra, 0 missing |
| no duplicate cache key | PASS |
| every record `phase == "formal"` | PASS |
| no smoke cache key present | PASS (disjoint from `runs/smoke/schedule.json`) |
| record filenames match the schedule | PASS |
| record `prompt_hash` == scheduled `prompt_hash` | PASS |
| record system/user prompt sha256 == `inputs/manifest.json` | PASS |
| schedule `prompt_hash` == manifest `combined_sha256` | PASS |
| `inputs/manifest.json` hash matches the formal freeze | PASS |
| single freeze across all 30 records | PASS: `formal_...` design `1940cf566a9c8f41` |
| git head at execution, working tree clean | `671804b`, clean on all 30 |
| request settings identical on all 30 | `temperature 0.7, max_tokens 4096, seed null` |
| scheduling seed string | `20260915:formal` |

## 2. Outcomes, tokens and recorded cost

| dataset | condition | n | success | refused | failed | truncated | model mismatch | attempts | prompt tok | cached | completion tok | cost USD |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| live_salmon | A | 5 | 5 | 0 | 0 | 0 | 0 | 5 | 27590 | 26880 | 7366 | 0.073788 |
| live_salmon | A_prime | 5 | 5 | 0 | 0 | 0 | 0 | 5 | 30205 | 29440 | 8739 | 0.086162 |
| live_salmon | B | 5 | 5 | 0 | 0 | 0 | 0 | 5 | 48060 | 47360 | 8446 | 0.092648 |
| dead_salmon | A | 5 | 5 | 0 | 0 | 0 | 0 | 5 | 27585 | 21504 | 5966 | 0.070642 |
| dead_salmon | A_prime | 5 | 5 | 0 | 0 | 0 | 0 | 5 | 30200 | 29440 | 6423 | 0.067624 |
| dead_salmon | B | 5 | 5 | 0 | 0 | 0 | 0 | 6 | 48055 | 42880 | 7027 | 0.088006 |
| **total** | | **30** | **30** | **0** | **0** | **0** | **0** | **31** | **211695** | **197504** | **43967** | **0.478870** |

- Cost is present on 30/30 records; no record has a missing cost, and none was recorded as zero by default. `is_byok: false` throughout.
- Rates implied by `cost_details` and reproduced exactly: $2.00/M input, $0.50/M cached input, $8.00/M output.
- Prompt tokens 5517-9612 against the 60,000 estimated-token ceiling; the `ceil(chars/1.4)` estimate stayed 1.34x-1.45x above actual in every cell.
- Completion tokens 1101-1926 of `max_tokens` 4096 (max 47% used), consistent with 0 truncations.
- Caveat on cost completeness: the recorded total sums the usage of successful responses. The one aborted attempt below may carry a provider-side charge that never reached a response body and is therefore not in this total. Reconcile against the OpenRouter activity page if an exact figure matters.

## 3. Retries and failures

One retry in the whole run, on the bounded technical-failure path:

- `dead_salmon/B` rep5: attempt 1 `transient_error` (TransientFailure: RemoteProtocolError: peer closed connection without sending complete message body (incompl...), attempt 2 success. Final `finish_reason=stop`, not truncated, 6490 chars.

Attempt outcomes across the run: `success`, `transient_error`. No `permanent_error`, no `refusal`. No record was retried on the basis of its content, and `--retry-failed` was never needed.

## 4. Response completeness and undeclared refusals

- All 30 papers non-empty, 5,239-8,226 characters, 761-1,158 words.
- All 30 contain Abstract, Methods, Results, Discussion and Limitations sections.
- All 30 carry `finish_reason: stop` and `native_finish_reason: completed`; the protocol `refusal` field is null on all 30.
- Scanned every paper for assistant-voice refusal language not captured by the protocol field ("I cannot", "I'm unable", "as an AI", "unable to assist", "I apologise, but"): **0 hits**. Scientific hedging such as "we cannot determine causality" was deliberately not counted as a refusal.
- 24 of 30 papers end with a markdown `---` rule after a complete closing sentence. That is formatting, not truncation; it was checked explicitly.

## 5. Review export

- Export: `review/formal/export_20260915T144035Z` -- 30 papers, 30 blank forms, `EXPORT_INFO.json`, `README_REVIEWER.md`.
- Mapping: `review/formal/mapping/mapping_20260915T144035Z.json`, outside the export directory.
- Exported count == scorable records == 30. Nothing was withheld: 0 off-plan records, 0 refused records, 0 failed records. Every scorable record appears exactly once.
- Each exported paper is byte-identical to the `content` of its record, and matches the `paper_sha256` recorded in the mapping.
- Review IDs are random 6-hex tokens, export order is shuffled and differs from the schedule order, and no exported file contains a dataset name, condition name, model identifier, repetition index or cache key.
- Forms are blank; `LOCK.json` and `unmasked_reviews.json` are absent, as they must be before scoring.

### Known limit on blinding, measured

The design states that review is label-hidden rather than blind because paper content can reveal the condition. Measured on this export:

- **13 of 30** papers quote the prompt's neutral dataset label verbatim ("Research Dataset A" / "Research Dataset B"). This lets a reviewer group papers by dataset. It does **not** say which of the two is the null dataset -- that mapping is only in the mapping file.
- **8 of 30** papers refer to the second-order correlation table or to "210" terms, which identifies condition B.

Neither is a defect in the export, and neither was altered: paper text is preserved verbatim by design. Reviewers should score each paper on what it asserts and resist letting a shared label group papers together, as `RUBRIC.md` and `README_REVIEWER.md` already instruct.

## 6. What was deliberately not done

No scores were filled, `lock-reviews` and `unmask` were not run, no per-condition findings were summarised, and no frozen prompt, rubric or design file was touched. Both freezes still verify against the working tree.

