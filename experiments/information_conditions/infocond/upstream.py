"""Access to upstream code without modifying it.

* ``prepare_summary`` is imported directly from src/prepare_data_summary.py.
* Prompt constants and the model table are read from src/run_ai_scientists.py
  with ``ast`` so that importing them does not require ``httpx`` and does not
  execute upstream module code.
* The dataset generator's functions are imported from datasets/.
"""
from __future__ import annotations

import ast
import importlib
import sys
from functools import lru_cache
from types import ModuleType

from .paths import DATASETS_DIR, UPSTREAM_SRC

_RUNNER_CONSTANTS = ("SYSTEM_PROMPT", "USER_PROMPT_TEMPLATE", "MODELS", "RUNS_PER_MODEL", "DATASETS")


def _ensure_path(p) -> None:
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)


@lru_cache(maxsize=None)
def summary_module() -> ModuleType:
    _ensure_path(UPSTREAM_SRC)
    return importlib.import_module("prepare_data_summary")


def prepare_summary(csv_path: str, dataset_label: str) -> str:
    """The unchanged upstream summary function (condition A)."""
    return summary_module().prepare_summary(csv_path, dataset_label)


@lru_cache(maxsize=None)
def generator_module() -> ModuleType:
    _ensure_path(DATASETS_DIR)
    return importlib.import_module("generate_live_salmon_data")


@lru_cache(maxsize=None)
def runner_constants() -> dict:
    """Literal constants from src/run_ai_scientists.py, extracted with ast."""
    src_path = UPSTREAM_SRC / "run_ai_scientists.py"
    tree = ast.parse(src_path.read_text(), filename=str(src_path))
    found: dict = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in _RUNNER_CONSTANTS:
                found[target.id] = ast.literal_eval(node.value)
    missing = [k for k in _RUNNER_CONSTANTS if k not in found]
    if missing:
        raise RuntimeError(f"Could not extract {missing} from {src_path}")
    return found


def upstream_models() -> dict:
    return dict(runner_constants()["MODELS"])


def system_prompt() -> str:
    return runner_constants()["SYSTEM_PROMPT"]


def user_prompt_template() -> str:
    return runner_constants()["USER_PROMPT_TEMPLATE"]
