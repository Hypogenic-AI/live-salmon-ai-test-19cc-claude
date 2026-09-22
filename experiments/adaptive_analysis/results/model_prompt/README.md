# Published model/prompt experiment evidence

This directory contains the completed study's English report tables, protocol,
metrics and trajectories. The compressed [evidence package](evidence/README.md)
contains **all 216 original raw records**: 180 formal and 36 development episodes,
including invalid model responses and request failures. It also retains the
frozen experiment source, dependency lock, exact requests, schedules and costs.

| File | Purpose |
|---|---|
| [../../REPORT.md](../../REPORT.md) | Main results, interpretation and limitations |
| [TABLES.md](TABLES.md) | All condition-level outcomes, resources and paired differences |
| [protocol.json](protocol.json) | Frozen settings, prompts, schedules and source hashes |
| [metrics.json](metrics.json) | Full machine-readable results and provenance |
| [TRAJECTORIES.md](TRAJECTORIES.md) | Every development/formal attempt and submitted explanation |
| [EXPLANATION_REVIEW.md](EXPLANATION_REVIEW.md) | Targeted assistant-assisted review and all 16 contradictory explanations |
| [explanation-review.json](explanation-review.json) | All 180 review labels, selected/minimum evidence and original explanations |
| [evidence/](evidence/) | Lossless compact raw archive, frozen source, restore utility and integrity checks |

## Rebuild the results without an API key

From the repository root, using the existing environment:

```bash
uv sync --frozen --no-install-project

# Choose a new output directory; the utility refuses to overwrite existing data.
.venv/bin/python experiments/adaptive_analysis/results/model_prompt/evidence/restore.py \
  experiments/adaptive_analysis/artifacts/published-replay

# Use the frozen experiment source, rather than today's revised checkout.
.venv/bin/python -B experiments/adaptive_analysis/scripts/report_model_prompt.py \
  experiments/adaptive_analysis/artifacts/published-replay/raw \
  experiments/adaptive_analysis/artifacts/published-report \
  --repo experiments/adaptive_analysis/artifacts/published-replay/source/live-salmon \
  --require-complete
```

Restoration verifies the original raw-file hashes. The report validates the
216 episode identities, source/configuration/prompt hashes, paired data, progress
inventories and reported usage. The auxiliary minimum-CV reference regenerates
the deterministic held-out data and predicts from **saved coefficients**; it
does not refit statistical models. Neither command invokes an LLM or reads an
API credential. The complete reporter is also restored under `tools/`.

The regenerated report includes detailed explanation evidence packets; the
separate targeted review labels are retained as analyst annotations and are
not recomputed by an LLM judge. Model-authored explanations are evidence, not
endorsed scientific conclusions.

## Why the raw archive is deduplicated

Fixed configurations fit the same candidates on the same data, so copying every
candidate record into every episode creates a large redundant archive. The
compact package stores exact candidate records in shared banks and preserves
the references and ordering needed to reconstruct each original episode.
Different values are retained, not rounded or merged approximately. Original
responses, including malformed JSON, remain unchanged. Restoration verifies
byte-level SHA-256 hashes before the offline report is accepted.

Historical absolute paths in raw records are provenance only; restoration and
reporting enumerate the supplied directories instead of accessing those paths.
The archived original execution wrapper is preserved as provenance; use the
current [matrix driver](../../scripts/run_matrix.py) for new paid experiments.

## Scope of this archive

The complete raw archive covers the later model/prompt study. The preceding
[pilot summaries](../pilot/REPORT.md) are separate and are not pooled into these
outcomes. Each main cell has five seeds and one model sample per seed. Failed
submissions stay in planned denominators, while MSE and false-selection means
show their successful, applicable denominators.

The provider reported $29.0650515 across 549 calls; five additional timeout
requests have unknown cost. This is a known subtotal, not the complete bill.
See the [main report](../../REPORT.md) for protocol failures, timeout counts,
resource tradeoffs and interpretation limits.
