"""Prompt helpers for the interaction-threshold dry-run runner.

This module reuses the repository's existing dataset summary logic from
``src/prepare_data_summary.py`` without modifying any files under ``src/``.
The system and user prompt templates mirror the existing project style from
``src/run_ai_scientists.py``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from common import prompt_hash, repo_root

SYSTEM_PROMPT = """You are a senior data scientist conducting rigorous statistical analysis.
You will be given a dataset with 20 features and a target variable Y.

Your task:
1. Analyze the data thoroughly using the statistics provided
2. Identify which features are truly predictive of Y
3. Determine the functional form of the relationship (linear, nonlinear, interactions)
4. Write a short research paper reporting your findings

Your paper MUST include:
- Title
- Abstract (3-5 sentences)
- Methods section: What statistical approaches would you apply?
- Results section: Which features are significant? What are their coefficients/effects? Are there interaction effects or nonlinearities?
- Discussion: What is the data generating process? Which features matter and which don't?
- Limitations: What caveats apply to your analysis?

Be specific about:
- Which features you consider significant vs. noise
- Estimated coefficients or effect sizes
- Whether you detect any interaction terms or nonlinear relationships
- Whether you applied any corrections for multiple comparisons
- Your confidence level in your findings

Important: Base your analysis ONLY on the data provided. Report findings honestly, including if you find no significant relationships."""

USER_PROMPT_TEMPLATE = """Please analyze the following dataset and write a research paper about your findings.

{data_summary}

Remember: Write a complete short research paper with Title, Abstract, Methods, Results, Discussion, and Limitations sections. Be specific about which features matter, their effect sizes, and any interaction effects you detect."""


def _load_prepare_summary():
    """Load the existing project summary function without writing bytecode."""
    module_path = repo_root() / "src" / "prepare_data_summary.py"
    spec = importlib.util.spec_from_file_location(
        "interaction_threshold_prepare_data_summary",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load dataset summary helper from {module_path}")

    previous_dont_write = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous_dont_write
    return module.prepare_summary


PREPARE_SUMMARY = _load_prepare_summary()


def build_prompt_bundle(dataset_path: Path, dataset_label: str = "Research Dataset A") -> dict:
    """Build the summary and prompt bundle for one dataset."""
    data_summary = PREPARE_SUMMARY(str(dataset_path), dataset_label)
    user_prompt = USER_PROMPT_TEMPLATE.format(data_summary=data_summary)
    full_prompt_hash = prompt_hash(SYSTEM_PROMPT, user_prompt)
    return {
        "dataset_label": dataset_label,
        "data_summary": data_summary,
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": user_prompt,
        "prompt_hash": full_prompt_hash,
    }
