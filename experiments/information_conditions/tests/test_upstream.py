import pytest

from infocond import upstream


def test_ast_constants_match_imported_module():
    pytest.importorskip("httpx")
    import importlib, sys
    sys.path.insert(0, str(upstream.UPSTREAM_SRC))
    mod = importlib.import_module("run_ai_scientists")
    c = upstream.runner_constants()
    assert c["SYSTEM_PROMPT"] == mod.SYSTEM_PROMPT
    assert c["USER_PROMPT_TEMPLATE"] == mod.USER_PROMPT_TEMPLATE
    assert c["MODELS"] == mod.MODELS
    assert c["RUNS_PER_MODEL"] == mod.RUNS_PER_MODEL


def test_selected_model_is_from_upstream_table(cfg):
    models = upstream.upstream_models()
    assert cfg["model_key"] in models
    assert models == {"gpt-4.1": "openai/gpt-4.1", "claude-sonnet-4.5": "anthropic/claude-sonnet-4.5",
                      "gemini-2.5-pro": "google/gemini-2.5-pro-preview"}


def test_request_settings_match_upstream(cfg):
    assert cfg["request_settings"]["temperature"] == 0.7
    assert cfg["request_settings"]["max_tokens"] == 4096
    assert cfg["request_settings"]["seed"] is None
