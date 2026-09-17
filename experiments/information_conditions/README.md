# Information-Conditions Experiment

This experiment studies whether progressively richer statistical summaries change the claims made by a language model about a known interaction in the Live Salmon datasets.

The model receives a statistical summary and writes a short scientific paper. It does not run code or analyze the raw dataset itself. The experiment therefore measures how the supplied information affects the model's written conclusions. It does not, by itself, distinguish a failure to notice evidence from a failure to reason correctly about that evidence.

The experiment is based on upstream commit `c88a910fc9eef390b8020645639a556fb7e393e4`. All experiment-specific code and files are contained in `experiments/information_conditions/`.

Results live in [`REPORT.md`](REPORT.md); this file covers setup and reproduction.

## Conditions

All conditions use the upstream system prompt and paper-writing template unchanged. They differ only in the statistical summary supplied to the model.

| Condition | Additional information |
| --- | --- |
| `A` | The original upstream summary produced by `src/prepare_data_summary.py::prepare_summary`. |
| `A_prime` | Condition A plus the sample size, the in-sample R² from an OLS model of `Y` on `X1`-`X20`, and correlations between squared residuals and squared predictors, `corr(e², Xi²)`. |
| `B` | Condition A_prime plus the Pearson correlation between `Y` and all 210 second-order terms: 20 squares and 190 pairwise products. |

The appended statistics are labelled as supplied precomputed results. The prompts do not contain the ground-truth formula, coefficients, dataset identity, or any other answer key. The generation tests check for these forms of leakage.

The condition names `A`, `A_prime`, and `B` are separate from the neutral dataset labels used in the upstream prompts.

## Model and request settings

The formal experiment uses `openai/gpt-4.1`, selected from the upstream model table. Requests use the upstream temperature of `0.7` and `max_tokens=4096`. No provider seed is supplied, so repetitions are independent samples rather than seed-controlled replications.

The requested model, returned model, provider, finish reason, usage, and raw response are recorded for every call. Execution refuses a model whose resolved identifier does not match the frozen experiment configuration.

## Datasets

The upstream repository commits short dataset samples but does not commit the 1,000-row CSV files used by the summary function. `cli.py verify-data` regenerates the full datasets with the upstream generator, seed, and generation order. It writes only missing gitignored CSV files and verifies them against the committed samples and baseline statistics.

Dataset hashes and verification results are stored in `inputs/manifest.json`. Machine-specific information, such as the current git state and observed package versions, is stored separately in `inputs/provenance.json`.

The regenerated data should be treated as a reproducible reconstruction of the upstream inputs, rather than as a newly committed copy of the original 1,000-row files. The original files are not available for a direct byte comparison.

## Environment

The experiment was run with:

- Python 3.13
- NumPy 2.4.3
- pandas 3.0.1

These versions are declared in `config.json` because pandas controls the text rendering of the upstream summary and NumPy controls the random-number stream used to generate the datasets. A version mismatch produces a warning during input generation and blocks execution.

The runtime environment does not install pytest through the upstream project configuration. Install it separately when running the offline test suite.

## Reproducing the setup

From the repository root:

```bash
uv sync --frozen --python 3.13
uv pip install --python .venv/bin/python pytest

PY=.venv/bin/python

$PY experiments/information_conditions/cli.py verify-data
$PY -m pytest experiments/information_conditions/tests -q
```

To construct a new set of prompts and its manifest:

```bash
$PY experiments/information_conditions/cli.py generate-inputs
```

This command writes the input files and manifest. It should only be run when intentionally creating or regenerating a design.

To preview a new run without making API calls:

```bash
$PY experiments/information_conditions/cli.py run --phase smoke
$PY experiments/information_conditions/cli.py run --phase formal
```

Execution requires a design freeze and an OpenRouter API key. A new run follows this sequence:

```bash
$PY experiments/information_conditions/cli.py freeze \
  --phase smoke \
  --note "initial design"

export OPENROUTER_KEY=...

$PY experiments/information_conditions/cli.py run \
  --phase smoke \
  --execute
```

After the smoke run has been checked, create and commit a formal freeze before starting the formal phase. Any change to a design file invalidates the freeze and requires a new one; `cli.py verify-freeze --phase <phase>` reports the current status. The set of files covered by the design hash is listed in [`CHANGES.md`](CHANGES.md). Existing run records and review files should be preserved as historical outputs.

## Execution records

Each call is written to `runs/<phase>/records/` with the prompt hashes, the requested and returned model identifiers, provider and finish reasons, token usage and reported cost, every attempt including technical errors, the raw response, and the design freeze and git state in force at the time.

Technical failures are retried at most three times with bounded backoff. Explicit provider refusals are terminal outcomes, recorded separately from technical failures and never retried, including under `--retry-failed`. Responses truncated by the token limit are recorded with a truncation flag and the returned text is never modified; they remain eligible for scoring and are counted separately in the report.

## Review workflow

The scoring materials are:

* `RUBRIC.md`: definitions for claim strength, interaction targets, proxy terms, structural explanations, and auxiliary checks;
* `review_schema.json`: allowed field values;
* `review_template.md`: the per-paper review form;
* `report_template.md`: the required report structure.

Export papers for review with:

```bash
$PY experiments/information_conditions/cli.py export-review \
  --phase formal
```

The export uses random paper IDs and a shuffled order. The mapping from paper IDs to the original run is stored separately. Because the paper text can reveal the condition or dataset, this is label-hidden review rather than complete blinding.

After all forms are complete:

```bash
$PY experiments/information_conditions/cli.py lock-reviews \
  --export-dir <export-directory>

$PY experiments/information_conditions/cli.py unmask \
  --export-dir <export-directory> \
  --mapping <mapping-file>
```

`lock-reviews` records the hashes of the completed forms. `unmask` requires a matching lock and then produces the condition-level summary.

This section describes the workflow the tooling supports. It is not a description of how the formal round was actually scored: most of those forms were completed by a model rather than a human, and the split is stated in [`REPORT.md`](REPORT.md).

The formal results and post-unmask verification are documented in [`REPORT.md`](REPORT.md) and [`review/formal/export_20260915T144035Z/VERIFICATION_POST_UNMASK.md`](review/formal/export_20260915T144035Z/VERIFICATION_POST_UNMASK.md).

## Limitations

This is an exploratory study with one model, two fixed datasets, and five repetitions per condition-dataset combination. The conditions change the amount and form of information available to the model, as well as the length and structure of the prompt, so they do not isolate a single causal factor.

The second-order correlation table also contains terms involving proxy variables. A correlation with a product term alone cannot establish that the term reflects the underlying data-generating mechanism.

The model identifier does not guarantee a fixed backend over time. The returned model and provider are recorded so that possible backend changes remain visible in the run records.

Limitations affecting the interpretation of the results, including how the papers were scored, are set out in [`REPORT.md`](REPORT.md).

## Directory structure

| Path | Purpose |
| --- | --- |
| `infocond/` | Experiment implementation |
| `tests/` | Offline tests with mocked API transport |
| `inputs/` | Generated prompts, manifest, and provenance |
| `runs/` | Smoke and formal execution records |
| `freezes/` | Design-freeze records |
| `review/` | Label-hidden paper exports, forms, mappings, and summaries |
| `RUBRIC.md` | Review criteria |
| `REPORT.md` | Experimental report |
| `CHANGES.md` | Implementation and review history |
