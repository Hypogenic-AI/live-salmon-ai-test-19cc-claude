"""Reproduce the frozen model/prompt matrix; dry-run unless --execute is given.

Run from the repository root with:
    python -m experiments.adaptive_analysis.scripts.run_matrix
Execution uses OPENROUTER_KEY from the environment and writes local artifacts.
"""

from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from functools import partial
import argparse
import hashlib
import importlib.metadata
import io
import itertools
import json
import multiprocessing
import os
from pathlib import Path
import random
import subprocess
import sys
import tarfile

DRIVER = Path(__file__).resolve()
REPO = DRIVER.parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments.adaptive_analysis import run

PROFILES = ["gpt4.1", "sol_medium", "astra_medium"]
VARIANTS = ["P0", "P1"]
CONDITIONS = ["global", "conditional", "null"]
WORKFLOWS = ["fixed", "adaptive"]
DEVELOPMENT_SEED = 9010
FORMAL_SEEDS = list(range(301, 306))
DEVELOPMENT_ORDER_SEED = 2026092201
FORMAL_ORDER_SEED = 2026092202
WORKERS = 3


def jobs(seeds, shuffle_seed):
    result = list(itertools.product(seeds, CONDITIONS, PROFILES, VARIANTS, WORKFLOWS))
    random.Random(shuffle_seed).shuffle(result)
    return result


def driver_hash():
    return hashlib.sha256(DRIVER.read_bytes()).hexdigest()


def plan(output, execute=False):
    return {
        "mode": "execute" if execute else "dry_run",
        "output": str(output),
        "profiles": {p: run.asdict(run.profile_config(p, "P0")) for p in PROFILES},
        "prompt_variants": VARIANTS, "conditions": CONDITIONS, "workflows": WORKFLOWS,
        "development_seed": DEVELOPMENT_SEED, "seeds": FORMAL_SEEDS,
        "development_episode_count": 36, "formal_episode_count": 180,
        "episode_count": 216,
        "development_maximum_model_calls": 180, "formal_maximum_model_calls": 900,
        "maximum_model_calls": 1080, "parallel_workers": WORKERS,
        "development_order_seed": DEVELOPMENT_ORDER_SEED,
        "formal_order_seed": FORMAL_ORDER_SEED,
        "execution_order": "Seed-fixed randomized submission order; completion order depends on runtime.",
        "retry_policy": "No automatic retries, output repair, model fallback, or budget increase. Failed outputs are retained.",
        "development_gate": "Each profile must produce at least one valid protocol episode; no correctness-based gate. HTTP auth/credits/not-found errors stop queued work.",
        "scope": "Exploratory paired comparison of model configurations and the four-rule bundle; five seeds per condition; no significance claims.",
        "note": "Dry-run reads no credentials and makes no API calls or statistical fits."
                if not execute else "Execution requires OPENROUTER_KEY in the environment.",
    }


def freeze_sources(base, matrix_plan, fingerprint, frozen_driver_hash):
    files = (sorted((REPO / "experiments/adaptive_analysis").glob("*.py"))
             + sorted((REPO / "src").glob("*.py"))
             + sorted((REPO / "datasets").glob("*.py"))
             + [REPO / "pyproject.toml", REPO / "uv.lock", DRIVER])
    # Hash and archive the same bytes, including this driver outside run's glob.
    sources = {str(p.relative_to(REPO)): p.read_bytes() for p in files}
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in sources.items()}
    with tarfile.open(base / "source-snapshot.tar.gz", "w:gz") as archive:
        for name, data in sources.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    try:
        git_head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True,
            stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        git_head = None
    run.atomic_save(base / "freeze.json", {
        **matrix_plan,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": git_head, "code_hash": fingerprint,
        "driver_file": str(DRIVER.relative_to(REPO)),
        "driver_sha256": frozen_driver_hash, "source_file_sha256": hashes,
        "prompts": {v: run.system_prompt(v) for v in VARIANTS},
        "development_schedule": jobs([DEVELOPMENT_SEED], DEVELOPMENT_ORDER_SEED),
        "formal_schedule": jobs(FORMAL_SEEDS, FORMAL_ORDER_SEED),
        "python": sys.version,
        "dependencies": {n: importlib.metadata.version(n) for n in
                         ["numpy", "pandas", "scipy", "scikit-learn", "httpx", "threadpoolctl"]},
    })
    return (run.code_fingerprint() == fingerprint
            and hashes[str(DRIVER.relative_to(REPO))] == frozen_driver_hash
            and driver_hash() == frozen_driver_hash)


def worker(job, output, expected_hash, expected_driver_hash):
    if run.code_fingerprint() != expected_hash or driver_hash() != expected_driver_hash:
        return {"status": "blocked", "reason": "source_changed", "job": job}
    from experiments.adaptive_analysis.analysis import AnalysisSession
    from experiments.adaptive_analysis.data import make_case, make_summary
    from experiments.adaptive_analysis.evaluate import score_submission
    from src.run_ai_scientists import call_openrouter

    seed, condition, profile, variant, workflow = job
    config = run.profile_config(profile, variant)
    case = make_case(seed, condition, n_samples=config.n_samples, n_discovery=config.n_discovery)
    record = run.run_episode(
        case=case, seed=seed, condition=condition, workflow=workflow,
        config=config, output=Path(output), code_hash=expected_hash,
        session_factory=AnalysisSession, summary_factory=make_summary,
        scorer=score_submission,
        transport=partial(call_openrouter, **run.transport_options(config)))
    return {"job": job, "status": record["status"], "path": record["artifact_path"],
            "failure": record.get("failure"), "usage": record.get("usage"),
            "api_errors": [{"http_status": e.get("http_status"), "error_code": e.get("error_code")}
                           for e in record["events"]
                           if e["type"] == "model_call" and e.get("status") == "failed"]}


def stage(base, name, schedule, fingerprint, frozen_driver_hash):
    output = base / name
    output.mkdir(exist_ok=True)
    progress = []
    # Separate processes avoid global stdout redirection and BLAS limit collisions.
    with ProcessPoolExecutor(max_workers=WORKERS,
                             mp_context=multiprocessing.get_context("spawn")) as pool:
        pending = {pool.submit(worker, j, str(output), fingerprint, frozen_driver_hash): j
                   for j in schedule}
        for future in as_completed(pending):
            try:
                result = future.result()
            except Exception as exc:
                result = {"job": pending[future], "status": "worker_exception",
                          "exception_type": type(exc).__name__}
            progress.append(result)
            run.atomic_save(base / (name + "-progress.json"),
                            {"planned": len(schedule), "completed": progress})
            print(f'{name} {len(progress)}/{len(schedule)} {result["job"]}: {result["status"]}',
                  flush=True)
            hard_error = (result["status"] in {"worker_exception", "blocked"}
                          or any(e.get("http_status") in {401, 402, 403, 404}
                                 for e in result.get("api_errors", [])))
            if hard_error:
                for queued in pending:
                    queued.cancel()
                print("Infrastructure error: pending work cancelled; running episodes finish and raw records are retained.",
                      flush=True)
                return False
    return True


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--execute", action="store_true",
                     help="Run the 216-episode matrix; requires OPENROUTER_KEY.")
    cli.add_argument("--output", type=Path,
                     help="New output directory; defaults to ignored artifacts/model-prompt-<UTC timestamp>.")
    args = cli.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = args.output or REPO / "experiments/adaptive_analysis/artifacts" / ("model-prompt-" + stamp)
    matrix_plan = plan(base, args.execute)
    print(json.dumps(matrix_plan, indent=2), flush=True)
    if not args.execute:
        return 0
    # Check before importing transport/data/analysis or creating any artifacts.
    if not os.environ.get("OPENROUTER_KEY"):
        print("OPENROUTER_KEY is required for --execute; no episodes were run.", flush=True)
        return 2
    base.mkdir(parents=True, exist_ok=False)
    fingerprint = run.code_fingerprint()
    frozen_driver_hash = driver_hash()
    if not freeze_sources(base, matrix_plan, fingerprint, frozen_driver_hash):
        print("Source changed during freeze; no episodes were run.", flush=True)
        return 1
    if not stage(base, "development", jobs([DEVELOPMENT_SEED], DEVELOPMENT_ORDER_SEED),
                 fingerprint, frozen_driver_hash):
        return 1
    records = [json.loads(p.read_text()) for p in (base / "development").glob("*.json")]
    valid_profiles = {r["config"]["profile"] for r in records if r["status"] == "success"}
    if (set(PROFILES) != valid_profiles or run.code_fingerprint() != fingerprint
            or driver_hash() != frozen_driver_hash):
        print("Development protocol gate failed; formal experiment not started.", flush=True)
        return 1
    run.atomic_save(base / "formal-start.json", {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "code_hash": fingerprint, "driver_sha256": frozen_driver_hash,
        "development_successes": sum(r["status"] == "success" for r in records),
        "development_records": len(records),
    })
    print("Protocol check complete; starting 180 formal episodes without changing the frozen configuration.",
          flush=True)
    ok = stage(base, "formal", jobs(FORMAL_SEEDS, FORMAL_ORDER_SEED), fingerprint, frozen_driver_hash)
    print("Experiment finished; all raw responses and costs are retained locally.", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
