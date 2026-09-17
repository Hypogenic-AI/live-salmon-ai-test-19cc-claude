"""Design freezes.

A freeze records a hash over every design file (code, config, generated prompts,
manifest, rubric, review schema/template) plus the git commit.  Execution of a
phase requires a freeze for that phase whose design hash still matches the
working tree.  Any later fix therefore forces a new, documented freeze.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .common import read_json, sha256_file, sha256_text, canonical_json, utc_now, utc_stamp, write_json
from .paths import EXP_DIR, FREEZES_DIR, REPO_ROOT

DESIGN_GLOBS = ["infocond/*.py", "cli.py", "config.json", "inputs/*.txt", "inputs/manifest.json",
                "RUBRIC.md", "review_schema.json", "review_template.md", "report_template.md"]
# Paths (relative to the experiment dir) that may change without invalidating a freeze.
MUTABLE_PREFIXES = ("runs/", "review/", "freezes/")

# Deliberately NOT in DESIGN_GLOBS, and why:
#   inputs/provenance.json  environment record (git state, platform, observed versions); changing
#                           machine or committing must not invalidate a freeze.  The versions that
#                           do affect generation are declared in config.json::environment and are
#                           verified at generate and execute time.
#   REPORT.md               the working report, filled in after unmasking.  Its *structure* is
#                           frozen through report_template.md; freezing the filled report as well
#                           would make writing up the results look like a design change.
#   CHANGES.md, README.md   narrative; a freeze note is required separately by create_freeze().


class FreezeError(RuntimeError):
    pass


def design_file_hashes(exp_dir: Path = EXP_DIR) -> dict[str, str]:
    out: dict[str, str] = {}
    for pattern in DESIGN_GLOBS:
        for p in sorted(exp_dir.glob(pattern)):
            if p.is_file():
                out[str(p.relative_to(exp_dir))] = sha256_file(p)
    return out


def design_hash(exp_dir: Path = EXP_DIR) -> str:
    return sha256_text(canonical_json(design_file_hashes(exp_dir)))


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, check=True, capture_output=True, text=True).stdout


def experiment_dirty_paths(exp_dir: Path = EXP_DIR) -> list[str]:
    rel = exp_dir.relative_to(REPO_ROOT)
    try:
        out = _git("status", "--porcelain", "--untracked-files=all", "--", str(rel))
    except Exception as exc:  # noqa: BLE001
        raise FreezeError(f"git status failed: {exc}") from exc
    dirty = []
    for line in out.splitlines():
        path = line[3:].strip()
        inner = path[len(str(rel)) + 1:] if path.startswith(str(rel)) else path
        if inner.startswith(MUTABLE_PREFIXES):
            continue
        dirty.append(path)
    return dirty


def create_freeze(phase: str, note: str, *, allow_dirty: bool = False, exp_dir: Path = EXP_DIR,
                  freezes_dir: Path = FREEZES_DIR) -> Path:
    if not note or not note.strip():
        raise FreezeError("a freeze note documenting the reason is required")
    dirty = experiment_dirty_paths(exp_dir)
    if dirty and not allow_dirty:
        raise FreezeError("uncommitted design changes present; commit first or pass --allow-dirty (recorded):\n  " + "\n  ".join(dirty))
    head = _git("rev-parse", "HEAD").strip()
    files = design_file_hashes(exp_dir)
    rec = {"phase": phase, "note": note.strip(), "created_at": utc_now(), "git_head": head,
           "dirty_design_paths_at_freeze": dirty, "design_hash": sha256_text(canonical_json(files)), "files": files}
    freezes_dir.mkdir(parents=True, exist_ok=True)
    path = freezes_dir / f"{phase}_{utc_stamp()}.json"
    write_json(path, rec)
    return path


def latest_freeze(phase: str, freezes_dir: Path = FREEZES_DIR) -> tuple[Path, dict] | None:
    if not freezes_dir.exists():
        return None
    candidates = sorted(freezes_dir.glob(f"{phase}_*.json"))
    if not candidates:
        return None
    p = candidates[-1]
    return p, read_json(p)


def verify_freeze(phase: str, exp_dir: Path = EXP_DIR, freezes_dir: Path = FREEZES_DIR) -> tuple[bool, str, dict | None]:
    found = latest_freeze(phase, freezes_dir)
    if found is None:
        return False, f"no freeze record for phase {phase!r}; run: cli.py freeze --phase {phase} --note '...'", None
    path, rec = found
    current = design_hash(exp_dir)
    if current != rec["design_hash"]:
        changed = sorted(set(design_file_hashes(exp_dir).items()) ^ set(rec["files"].items()))
        names = sorted({k for k, _ in changed})
        return False, f"design changed since freeze {path.name}; changed files: {names}. Commit and create a new freeze.", rec
    return True, f"freeze {path.name} matches current design", {**rec, "freeze_file": path.name}
