"""
Run AI Scientists on Live/Dead Salmon Datasets.

Sends dataset summaries to multiple LLMs via OpenRouter API,
asking each to act as a data scientist and write a research paper.
"""

import hashlib
import json
import os
import sys
import time

import httpx

sys.path.insert(0, os.path.dirname(__file__))
from prepare_data_summary import prepare_summary

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

MODELS = {
    "gpt-4.1": "openai/gpt-4.1",
    "claude-sonnet-4.5": "anthropic/claude-sonnet-4.5",
    "gemini-2.5-pro": "google/gemini-2.5-pro-preview",
}

RUNS_PER_MODEL = 3
DATASETS = {
    "live_salmon": "datasets/live_salmon_data.csv",
    "dead_salmon": "datasets/dead_salmon_data.csv",
}

RESULTS_DIR = "results/papers"

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


def call_openrouter(
    model_id: str, system: str, user: str, run_id: int, *,
    temperature: float | None = 0.7, max_tokens: int = 4096,
    reasoning_effort: str | None = None,
) -> dict:
    """Call OpenRouter, preserving legacy defaults and safe response metadata.

    Reasoning and visible output share ``max_tokens`` on most providers. An
    empty completion can therefore still have billable usage and a length finish
    reason; retain both for the caller instead of discarding that response.
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/live-salmon-test",
    }
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if reasoning_effort is not None:
        payload["reasoning"] = {"effort": reasoning_effort}
    response_metadata = {}
    response_usage = {}

    def failure(code: str, http_status: int | None = None) -> dict:
        # Exceptions and API error messages may contain request bodies or keys.
        # Only locally defined codes and numeric HTTP status are safe to retain.
        print(f"    ERROR: {code}")
        return {
            "model": model_id, "run_id": run_id, "content": "",
            "usage": response_usage, "status": "error", "error": code,
            "error_code": code, "http_status": http_status,
            "actual_model": None, "provider": None, "generation_id": None,
            "finish_reason": None, "native_finish_reason": None,
            "refusal": False,
            **response_metadata,
        }

    def optional_string(value):
        return value if isinstance(value, str) else None

    print(f"  Calling {model_id} (run {run_id})...", flush=True)
    http_status = None
    try:
        resp = httpx.post(
            OPENROUTER_URL, json=payload, headers=headers, timeout=120.0
        )
        http_status = resp.status_code
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            return failure("invalid_response", http_status)
        usage = data.get("usage")
        response_usage = usage if isinstance(usage, dict) else {}
        response_metadata = {
            "actual_model": optional_string(data.get("model")),
            "provider": optional_string(data.get("provider")),
            "generation_id": optional_string(data.get("id")),
            "refusal": False,
        }
        if "error" in data:
            return failure("api_error", http_status)
        choice = data["choices"][0]
        response_metadata.update({
            "finish_reason": optional_string(choice.get("finish_reason")),
            "native_finish_reason": optional_string(choice.get("native_finish_reason")),
        })
        if "error" in choice or choice.get("finish_reason") == "error":
            return failure("api_error", http_status)
        message = choice["message"]
        response_metadata["refusal"] = bool(message.get("refusal"))
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            return failure("invalid_response", http_status)
        print(f"    Done. Tokens: {response_usage.get('total_tokens', '?')}")
        return {
            "model": model_id,
            "run_id": run_id,
            "content": content,
            "usage": response_usage,
            "status": "success",
            "http_status": http_status,
            **response_metadata,
        }
    except httpx.HTTPStatusError:
        return failure("http_error", http_status)
    except httpx.TimeoutException:
        return failure("request_timeout")
    except httpx.RequestError:
        return failure("request_error")
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        return failure("invalid_response", http_status)
    except Exception:
        return failure("unexpected_error", http_status)


def run_experiments():
    """Run all AI scientist experiments."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    all_results = []

    for dataset_name, dataset_path in DATASETS.items():
        label = "Research Dataset A" if "live" in dataset_name else "Research Dataset B"
        data_summary = prepare_summary(dataset_path, label)
        user_prompt = USER_PROMPT_TEMPLATE.format(data_summary=data_summary)

        print(f"\n{'='*60}")
        print(f"Dataset: {dataset_name}")
        print(f"{'='*60}")

        for model_name, model_id in MODELS.items():
            for run in range(1, RUNS_PER_MODEL + 1):
                # Check cache
                cache_key = f"{dataset_name}_{model_name}_run{run}"
                cache_path = os.path.join(RESULTS_DIR, f"{cache_key}.json")

                if os.path.exists(cache_path):
                    print(f"  Cached: {cache_key}")
                    with open(cache_path) as f:
                        result = json.load(f)
                else:
                    result = call_openrouter(model_id, SYSTEM_PROMPT, user_prompt, run)
                    result["dataset"] = dataset_name
                    result["model_name"] = model_name
                    result["cache_key"] = cache_key

                    # Save individual result
                    with open(cache_path, "w") as f:
                        json.dump(result, f, indent=2)

                    # Rate limit courtesy
                    time.sleep(2)

                all_results.append(result if isinstance(result, dict) else json.load(open(cache_path)))

    # Save combined results
    combined_path = os.path.join("results", "all_papers.json")
    with open(combined_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nSaved {len(all_results)} results to {combined_path}")

    # Print summary
    successes = sum(1 for r in all_results if r.get("status") == "success")
    errors = sum(1 for r in all_results if r.get("status") == "error")
    print(f"Successes: {successes}, Errors: {errors}")

    return all_results


if __name__ == "__main__":
    if not OPENROUTER_KEY:
        print("ERROR: OPENROUTER_KEY not set")
        sys.exit(1)
    run_experiments()
