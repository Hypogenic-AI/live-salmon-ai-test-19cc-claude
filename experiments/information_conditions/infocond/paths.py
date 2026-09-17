"""Filesystem layout.  Everything is resolved relative to this file so the CLI
works from any working directory."""
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parents[1]          # experiments/information_conditions
REPO_ROOT = Path(__file__).resolve().parents[3]        # repository root
UPSTREAM_SRC = REPO_ROOT / "src"
DATASETS_DIR = REPO_ROOT / "datasets"
UPSTREAM_RESULTS = REPO_ROOT / "results"

CONFIG_PATH = EXP_DIR / "config.json"
INPUTS_DIR = EXP_DIR / "inputs"
RUNS_DIR = EXP_DIR / "runs"
FREEZES_DIR = EXP_DIR / "freezes"
REVIEW_DIR = EXP_DIR / "review"
REVIEW_SCHEMA_PATH = EXP_DIR / "review_schema.json"
REPORT_PATH = EXP_DIR / "REPORT.md"
