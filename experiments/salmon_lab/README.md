# Live Salmon Lab

AI scientists that explore a world instead of analysing a given dataset. The agent designs its own experiments, analyses the data in its own code, and submits a paper; in the physics world it also submits the law it has inferred, as code. Two worlds are included: the original Live Salmon formula made explorable (the statistical world), and a physics laboratory with a newly added law. The design and the results are described in [REPORT.md](REPORT.md).

## Reproducing the results

Scoring runs offline from the saved episodes and makes no API calls. From the repository root:

```sh
uv run --with pytest pytest experiments/salmon_lab
uv run python experiments/salmon_lab/score.py --summary
uv run python experiments/salmon_lab/physics_score.py
uv run python experiments/salmon_lab/reference.py
uv run python experiments/salmon_lab/physics_reference.py
```

The last two commands simulate the scripted data-collection strategies of REPORT.md §3.2 and §4.3.

## Running new episodes

New episodes require Docker, for the sandbox in which the agent's code is executed, and an OpenRouter key (`OPENROUTER_API_KEY`) in a git-ignored `.env` file at the repository root. Without `--execute`, the scripts make no API calls: a scripted stand-in plays the agent, and the resulting transcript is written to `dry_run/`.

```sh
docker build -t salmon-lab-sandbox:1 experiments/salmon_lab/sandbox
uv run python experiments/salmon_lab/explore.py --execute --model claude-sonnet-5.5 --variant python --runs 6
uv run python experiments/salmon_lab/physics_explore.py --execute --model claude-sonnet-5.5 --condition kappa2 --runs 6
```

- Statistical world (`--variant`): `unlimited` (fixed tools), `python` (fixed tools and Python), `base` (pilot episodes).
- Physics world (`--condition`): `base`, `stated_error`, `kappa2`, `kappa2_stated_error`, `kappa0`, `kappa0_stated_error`.

Episode *k* uses random seed *k*, and episodes already saved are skipped.

## Files

| File | Content |
|---|---|
| `world.py`, `prompts.py`, `explore.py`, `score.py`, `reference.py` | Statistical world: laboratory, prompts, exploration loop, scoring, scripted strategies |
| `physics_world.py`, `physics_prompts.py`, `physics_explore.py`, `physics_score.py`, `physics_reference.py` | Physics world, with the same structure |
| `sandbox.py`, `sandbox/` | Docker sandbox: no network, read-only file system, unprivileged user, memory, CPU and time limits |
| `test_*.py` | Offline tests |
| `figures/` | Figures 1 and 2 of REPORT.md |
| `results/<variant>/<model>/run<k>.json` | Episodes in the statistical world |
| `results/physics/<condition>/<model>/run<k>.json` | Episodes in the physics world |

Each episode file contains the full conversation, every run, every block of code with its output, the token usage and the cost; the corresponding `.score.json` file contains its score.
