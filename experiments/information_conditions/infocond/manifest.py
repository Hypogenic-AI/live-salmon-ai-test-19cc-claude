"""Two separate records of the six model inputs.

``inputs/manifest.json`` is the *design* record and is covered by the design
hash: it holds only things that are properties of the experiment (upstream
commit, model, request settings, dataset content hashes, prompt hashes and the
supplied tables, the required package versions).

Reproducibility, stated precisely: re-running ``generate-inputs`` on an unchanged
design reproduces this file byte for byte **on a machine whose numpy and pandas
match config.json::environment and whose linear algebra agrees to within
1e-12**.  It is not byte-reproducible across arbitrary BLAS builds unless the
stored statistics are rounded, which is why format v2 normalises every float
(see MANIFEST_FLOAT_DECIMALS).  Format v1, used for the committed 2026-09-15
record, stored raw float64 and did drift in the last digit between platforms.

``inputs/provenance.json`` is the *environment* record and is deliberately
outside the design hash: git state, platform, observed package versions and
whether the gitignored CSVs happened to be regenerated on this invocation.
None of that changes the experiment, so none of it may invalidate a freeze.
"""
from __future__ import annotations

import importlib
import json
import platform
import subprocess
import sys

from .common import sha256_file, sha256_text, utc_now, write_json, write_text
from .conditions import input_basename
from .paths import EXP_DIR, INPUTS_DIR, REPO_ROOT, UPSTREAM_RESULTS
from . import upstream

PROVENANCE_FILE = "inputs/provenance.json"

# Design-record format. v1 stored raw float64 from numpy linear algebra; those differ in
# the last ulp between BLAS builds, so a rebuild on another machine produced a different
# byte stream and therefore a different design hash even when all six prompts were
# identical. v2 rounds every float in the record to MANIFEST_FLOAT_DECIMALS before it is
# written. The prompts themselves are unaffected: they are rendered at cfg["decimals"]
# (4) and were always stable.
MANIFEST_FORMAT_VERSION = 2
MANIFEST_FLOAT_DECIMALS = 12


def normalise_floats(obj, decimals: int = MANIFEST_FLOAT_DECIMALS):
    """Round every float in a nested structure so the record is byte-reproducible.

    12 decimals is far beyond the 4 the prompts use and far beyond any difference that
    could matter for checking, while being coarse enough to absorb last-ulp variation
    between platforms.  -0.0 is folded to 0.0 so the sign of a rounded zero cannot
    change the hash either.
    """
    if isinstance(obj, bool) or obj is None:
        return obj
    if isinstance(obj, float):
        r = round(obj, decimals)
        return 0.0 if r == 0 else r
    if isinstance(obj, dict):
        return {k: normalise_floats(v, decimals) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [normalise_floats(v, decimals) for v in obj]
    return obj


def package_versions() -> dict:
    out = {"python": sys.version.split()[0], "platform": platform.platform()}
    for mod in ("numpy", "pandas", "httpx", "scipy", "sklearn"):
        try:
            out[mod] = getattr(importlib.import_module(mod), "__version__", "unknown")
        except Exception:  # noqa: BLE001 - absence is informative, not fatal
            out[mod] = None
    return out


def python_minor() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def environment_problems(cfg: dict) -> list[str]:
    """Mismatches against the versions config.json declares part of the design.

    Only numpy and pandas are checked: numpy's ``default_rng`` stream produces
    the datasets and pandas renders condition A.  Everything else is recorded
    but not constrained.
    """
    env = cfg.get("environment")
    if not env:
        return []
    problems = []
    want_py = env.get("python_minor")
    if want_py and python_minor() != want_py:
        problems.append(f"python {python_minor()} but the design requires {want_py} "
                        f"(uv.lock resolves different numpy/pandas below 3.11)")
    observed = package_versions()
    for name, want in (env.get("required_packages") or {}).items():
        got = observed.get(name)
        if got != want:
            problems.append(f"{name} {got} but the design requires {want}")
    return problems


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=REPO_ROOT, check=True, capture_output=True, text=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return None


def git_info() -> dict:
    status = _git("status", "--porcelain")
    return {
        "head_commit": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "working_tree_dirty": bool(status) if status is not None else None,
        "origin_url": _git("remote", "get-url", "origin"),
    }


def upstream_calibration(cfg: dict) -> dict:
    """Observed prompt_tokens for the upstream condition-A prompt, per model, taken
    from the committed upstream paper records.  Used only to justify the
    chars-per-token estimate; never used as an input."""
    consts = upstream.runner_constants()
    out = {}
    for key in consts["MODELS"]:
        p = UPSTREAM_RESULTS / "papers" / f"live_salmon_{key}_run1.json"
        if p.exists():
            rec = json.loads(p.read_text())
            out[key] = {"file": str(p.relative_to(REPO_ROOT)), "prompt_tokens": rec.get("usage", {}).get("prompt_tokens")}
    return out


def build_manifest(cfg: dict, bundles: list[dict], data_info: dict, verification: dict) -> dict:
    consts = upstream.runner_constants()
    model_key = cfg["model_key"]
    a_bundle = next(b for b in bundles if b["condition"] == "A" and b["dataset"] == "live_salmon")
    calib = upstream_calibration(cfg)
    chars_A = a_bundle["chars"]["combined"]
    for k, v in calib.items():
        if v.get("prompt_tokens"):
            v["implied_chars_per_token_for_condition_A"] = round(chars_A / v["prompt_tokens"], 3)
    inputs = []
    for b in bundles:
        base = input_basename(b["dataset"], b["condition"])
        inputs.append({
            "dataset": b["dataset"],
            "condition": b["condition"],
            "dataset_label_in_prompt": b["dataset_label_in_prompt"],
            "user_prompt_file": f"inputs/{base}.user.txt",
            "system_prompt_file": "inputs/system_prompt.txt",
            "hashes": b["hashes"],
            "chars": b["chars"],
            "estimated_input_tokens": b["estimated_input_tokens"],
            "details": _manifest_details(b["details"]),
        })
    return normalise_floats({
        "manifest_format_version": MANIFEST_FORMAT_VERSION,
        "experiment": cfg["experiment"],
        "upstream_url": cfg["upstream_url"],
        "upstream_baseline_commit": cfg["upstream_commit"],
        "model": {"key": model_key, "id": consts["MODELS"][model_key], "upstream_models": consts["MODELS"],
                  "upstream_runs_per_model": consts["RUNS_PER_MODEL"]},
        "request_settings": cfg["request_settings"],
        "request_settings_note": cfg["request_settings_note"],
        "phases": cfg["phases"],
        "scheduling_seed": cfg["scheduling_seed"],
        "conditions": cfg["conditions"],
        "datasets": {k: {kk: vv for kk, vv in v.items() if kk in ("path",)} for k, v in data_info.items()},
        "dataset_verification": verification,
        "prompt_construction": {
            "system_prompt_source": "src/run_ai_scientists.py::SYSTEM_PROMPT (unchanged)",
            "user_prompt_source": "src/run_ai_scientists.py::USER_PROMPT_TEMPLATE (unchanged) with {data_summary} = condition text",
            "condition_A": "src/prepare_data_summary.py::prepare_summary(csv, label) unchanged",
            "condition_A_prime": "A + Part 1 (OLS with intercept on X1-X20, all n; in-sample R^2; corr(e^2, Xi^2) x20; n; no coefficients)",
            "condition_B": "A_prime + Part 2 (Pearson r of Y with 20 squares + 190 cross products, fixed index order, raw r and n only)",
            "decimals": cfg["decimals"],
        },
        "input_length": {**cfg["input_length"], "upstream_calibration_condition_A": calib},
        "inputs": inputs,
        "required_environment": cfg.get("environment", {}),
        "provenance_file": PROVENANCE_FILE,
        "provenance_note": ("Git state, platform, observed package versions and whether the gitignored CSVs "
                            "were regenerated on this invocation are recorded in " + PROVENANCE_FILE +
                            ", which is outside the design hash so that committing, cloning or re-running "
                            "generate-inputs cannot invalidate a freeze."),
        "config_sha256": sha256_file(EXP_DIR / "config.json"),
    })


def build_provenance(cfg: dict, bundles: list[dict], data_info: dict, manifest: dict) -> dict:
    """Environment record.  Never hashed into the design; never read back by any check."""
    return {
        "generated_at": utc_now(),
        "note": ("Observed environment at generation time. This file is intentionally excluded from the "
                 "design hash: nothing here changes the experiment. The design-relevant versions are "
                 "declared in config.json::environment and verified at generate and execute time."),
        "git": git_info(),
        "observed_package_versions": package_versions(),
        "python_minor": python_minor(),
        "environment_problems": environment_problems(cfg),
        "datasets_regenerated_now": {k: bool(v.get("regenerated_now")) for k, v in data_info.items()},
        "manifest_sha256_at_write": None,
        "input_hashes": {input_basename(b["dataset"], b["condition"]): b["hashes"]["combined_sha256"] for b in bundles},
    }


def _manifest_details(details: dict) -> dict:
    """Keep the manifest readable: counts and scalars only, plus the full tables
    (they are the supplied inputs and must be checkable)."""
    keep = {}
    for k, v in details.items():
        keep[k] = v
    return keep


def write_inputs(cfg: dict, bundles: list[dict], manifest: dict, provenance: dict | None = None) -> list[str]:
    INPUTS_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    system = bundles[0]["system_prompt"]
    write_text(INPUTS_DIR / "system_prompt.txt", system)
    written.append("inputs/system_prompt.txt")
    for b in bundles:
        base = input_basename(b["dataset"], b["condition"])
        write_text(INPUTS_DIR / f"{base}.user.txt", b["user_prompt"])
        written.append(f"inputs/{base}.user.txt")
    manifest_path = INPUTS_DIR / "manifest.json"
    write_json(manifest_path, manifest)
    written.append("inputs/manifest.json")
    if provenance is not None:
        provenance = {**provenance, "manifest_sha256_at_write": sha256_file(manifest_path)}
        write_json(EXP_DIR / PROVENANCE_FILE, provenance)
        written.append(PROVENANCE_FILE)
    return written


def verify_written_inputs(manifest: dict) -> list[str]:
    """Re-hash the files on disk against the manifest; return problems."""
    problems = []
    sys_hash = sha256_text((EXP_DIR / "inputs" / "system_prompt.txt").read_text())
    for item in manifest["inputs"]:
        p = EXP_DIR / item["user_prompt_file"]          # paths in the manifest are relative to the experiment dir
        if sha256_text(p.read_text()) != item["hashes"]["user_prompt_sha256"]:
            problems.append(f"{item['user_prompt_file']} hash mismatch")
        if sys_hash != item["hashes"]["system_prompt_sha256"]:
            problems.append("system_prompt.txt hash mismatch")
    return problems
