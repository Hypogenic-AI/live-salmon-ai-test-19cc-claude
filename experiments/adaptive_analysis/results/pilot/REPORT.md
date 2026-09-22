# Historical GPT-4.1 pilot

This earlier pilot motivated the model/prompt comparison in the
[main report](../../REPORT.md). Its outcomes are kept separate: it used different
seeds, a 4,096-token completion cap, and an earlier prompt. The current runner
is not a byte-identical reproduction of this historical configuration.

## Configuration and outcomes

The replacement pilot used requested model `openai/gpt-4.1`, temperature 0.7,
development seed 9003, and formal seeds 201–210. Both workflows used the same
700/300 discovery/test split and five-fold CV design as the later experiment.
The old transport did not record the resolved response model ID; that field
remains unknown in these records.

All 60 formal episodes completed successfully:

| Condition | A: exact structure / planned | B: exact structure / planned | A: mean test MSE | B: mean test MSE |
|---|---:|---:|---:|---:|
| Global | 3/10 | 10/10 | 1.016376 | 1.013030 |
| Conditional | 10/10 | 0/10 | 1.014190 | 1.318430 |
| Null | 0/10 | 0/10 | 1.037313 | 1.025743 |

All 30 adaptive episodes called the pairwise scan exactly once and none called
the stability scan. Every adaptive submission selected an interaction model,
with four to six analysis actions still available. Thus its global success did
not demonstrate reliable stopping or complexity selection across conditions.

A performed 650,160 numerical fits and made 30 model calls; B performed 34,404
fits and made 100 calls. Formal API costs were $0.641632 and $1.363728. The
pre-existing minimum-CV rule recovered 0/10 global, 10/10 conditional and 8/10
null cases from A's saved candidates. Neither LLM workflow consistently exceeded
that reference, and the reference itself overconditioned every global case.

## Disclosed interface revision

An earlier trial listed the diagnostic argument schemas without explaining
that pairwise scans all 190 pairs and stability scans 18 possible gates. It was
stopped after six development episodes and 17 formal-stage records (16 completed;
one intentionally interrupted during statistical fitting). Full tool semantics
were added before running the replacement on new seeds. These initial outcomes
were excluded from the replacement and later main experiment.

| Stage | Records | Model calls | Reported cost |
|---|---:|---:|---:|
| Superseded development, seed 9002 | 6 | 18 | $0.253550 |
| Superseded formal trial, seeds 101–103 | 17 | 53 | $0.743914 |
| Replacement development, seed 9003 | 6 | 13 | $0.198772 |
| Replacement formal pilot, seeds 201–210 | 60 | 130 | $2.005360 |
| Historical total, costs only | 89 | 214 | $3.201596 |

The replacement freeze recorded code hash
`184dabacce7cae10b281ac2f85e0787ac0f23c475bfbf53cc8d59b747ea0dd0b`
at `2026-09-22T00:53:19.772934+00:00`. No code or prompt changed during that
replacement run. The historical implementation passed 36 offline tests.

## Included supporting summaries

- [metrics.json](metrics.json): formal/development aggregates, paired rows, source provenance and historical spending.
- [TRAJECTORIES.md](TRAJECTORIES.md): action paths, submissions, and separate development/superseded records.
- [min-cv-reference.json](min-cv-reference.json): saved-coefficient auxiliary reference.
- [tool-usage.json](tool-usage.json): diagnostic usage and stopping behavior.

These are supporting summaries of the prior pilot. The complete compressed raw
archive and offline restoration provided with this PR cover the **later 216-record
model/prompt study**, not these 89 historical records. Historical spending and
outcomes are never pooled into the later study's results.
