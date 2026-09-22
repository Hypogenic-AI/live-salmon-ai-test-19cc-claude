"""Offline protocol tests: no live API access, private datasets, or credentials."""

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from experiments.adaptive_analysis.run import (
    Config, EpisodeError, build_config_hash, flatten_episode, main, parse_action,
    parser, run_episode, usage_totals, profile_config, system_prompt, transport_options,
)


class Frame:
    columns = ["X1", "X2", "X3", "Y"]

    def drop(self, columns):
        assert columns == ["Y"]
        return "held_out_predictors"


class Session:
    def __init__(self, discovery, seed, folds, top_k):
        self.records = {}
        self.exposed_model_ids = set()
        self.evidence_ids = set()
        self.stats = {"candidate_models": 0, "cv_fits": 0, "final_fits": 0,
                      "cache_hits": 0, "analysis_seconds": 0.0}

    def fit_model(self, spec):
        model = "m_" + spec["kind"]
        record = {"model_id": model, "spec": spec, "cv_mse": 1.0}
        self.records[model] = record
        self.exposed_model_ids.add(model)
        self.evidence_ids.add("fit:" + model)
        return {**record, "evidence_id": "fit:" + model}

    def fixed_evidence(self):
        public = self.fit_model({"kind": "linear"})
        self.records["hidden_model"] = {"model_id": "hidden_model", "private_sentinel": "NEVER_SEND"}
        self.evidence_ids.add("fixed:summary")
        return {"baselines": [public], "evidence_id": "fixed:summary"}

    def diagnose(self, model_id, mode, term=None):
        self.evidence_ids.add("diagnosis:1")
        return {"evidence_id": "diagnosis:1", "finding": "real_result_sentinel"}

    def predict(self, model_id, X):
        assert X == "held_out_predictors"
        return [0.0]


def response(action, **extra):
    return {"status": "success", "content": json.dumps(action),
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}, **extra}


def submit(model="m_linear"):
    return {"tool": "submit", "model_id": model,
            "evidence_ids": ["fit:" + model], "explanation": "CV evidence supports this model."}


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.output = Path(self.temp.name)
        self.case = SimpleNamespace(discovery=Frame(), test=Frame(),
                                    truth="PRIVATE_TRUTH", fingerprint="dataset_hash")
        self.score_calls = 0

    def tearDown(self):
        self.temp.cleanup()

    def score(self, case, record, predictions):
        self.score_calls += 1
        return {"test_mse": 1.0}

    def episode(self, transport=None, workflow="fixed", **kwargs):
        values = dict(case=self.case, seed=101, condition="conditional", workflow=workflow,
                      config=Config(max_steps=2), output=self.output, code_hash="codehash",
                      session_factory=Session, summary_factory=lambda _: {"rows": 700},
                      scorer=self.score, transport=transport)
        values.update(kwargs)
        return run_episode(**values)

    def parse(self, action, **kwargs):
        values = dict(features={"X1", "X2", "X3"},
                      allowed_tools={"fit_model", "diagnose", "submit"},
                      exposed_models={"m_linear"}, evidence_ids={"fit:m_linear", "fixed:summary"})
        values.update(kwargs)
        return parse_action(json.dumps(action), **values)

    def test_strict_actions_reject_extras_and_unexposed_references(self):
        invalid = [
            {"tool": "shell", "command": "anything"},
            {"tool": "fit_model", "spec": {"kind": "linear", "pair": ["X1", "X2"]}},
            {"tool": "fit_model", "spec": {"kind": "conditional", "pair": ["X1", "X2"], "gate": "X2"}},
            {"tool": "diagnose", "model_id": "m_linear", "mode": "stability"},
            {"tool": "diagnose", "model_id": "m_linear", "mode": "pairwise", "term": ["X1", "X2"]},
            submit("hidden_model"),
            {**submit(), "evidence_ids": ["fixed:summary"]},
            {**submit(), "extra": True},
        ]
        for action in invalid:
            with self.subTest(action=action), self.assertRaises(EpisodeError):
                self.parse(action)

    def test_duplicate_keys_and_nonfinite_values_rejected(self):
        for text in ['{"tool":"submit","tool":"submit"}', '{"tool":NaN}', '```json\n{}\n```']:
            with self.subTest(text=text), self.assertRaises(EpisodeError):
                parse_action(text, {"X1"}, allowed_tools={"submit"}, exposed_models=set(), evidence_ids=set())

    def test_fixed_calls_once_and_keeps_hidden_records_out_of_prompt(self):
        calls = []

        def transport(model, system, user, run_id):
            calls.append(json.loads(user))
            self.assertNotIn("NEVER_SEND", user)
            self.assertNotIn("PRIVATE_TRUTH", user)
            self.assertNotIn("conditional", user)
            self.assertEqual(self.score_calls, 0)
            return response(submit())

        result = self.episode(transport)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["requested_model"], "openai/gpt-4.1")
        self.assertIsNone(result["actual_model"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["allowed_tools"], ["submit"])
        self.assertIn("hidden_model", result["records"])
        self.assertEqual(self.score_calls, 1)

    def test_adaptive_next_prompt_contains_real_result_and_budget_ends(self):
        actions = [
            {"tool": "fit_model", "spec": {"kind": "linear"}},
            {"tool": "diagnose", "model_id": "m_linear", "mode": "pairwise"},
            submit(),
        ]
        prompts = []

        def transport(model, system, user, run_id):
            prompts.append(json.loads(user))
            return response(actions[len(prompts) - 1])

        result = self.episode(transport, "adaptive")
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(prompts), 3)
        self.assertEqual(prompts[0]["history"], [])
        self.assertEqual(prompts[1]["history"][0]["result"]["model_id"], "m_linear")
        self.assertIn("real_result_sentinel", json.dumps(prompts[2]))
        self.assertEqual(prompts[2]["allowed_tools"], ["submit"])
        self.assertEqual(result["usage"]["total_tokens"], 9)
        self.assertIsNone(result["usage"]["reported_cost"])

    def test_invalid_json_fails_without_scoring_or_automatic_retry(self):
        calls = []

        def transport(*_):
            calls.append(1)
            return {"status": "success", "content": "not JSON"}

        failed = self.episode(transport)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["failure"]["code"], "invalid_json")
        self.assertEqual(self.score_calls, 0)
        cached = self.episode(transport)
        self.assertEqual(len(calls), 1)
        self.assertEqual(cached["attempt"], 1)
        retried = self.episode(lambda *_: response(submit()), retry_failed=True)
        self.assertEqual(retried["status"], "success")
        self.assertEqual(retried["attempt"], 2)
        self.assertEqual(retried["previous_attempts"][0]["status"], "failed")
        self.assertEqual(self.score_calls, 1)
        flat = flatten_episode(retried)
        self.assertEqual(flat["attempt_count"], 2)
        self.assertEqual(flat["failed_attempt_count"], 1)
        self.assertEqual(flat["model_calls"], 2)
        self.assertIsNone(flat["input_tokens"])
        self.assertEqual(flat["latest_attempt_costs"]["input_tokens"], 2)

    def test_retry_costs_include_failed_attempt_and_preserve_latest_costs(self):
        usage = {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7, "cost": 0.01}
        self.episode(lambda *_: {"status": "success", "content": "invalid JSON", "usage": usage})
        final = self.episode(lambda *_: response(submit(), usage=usage), retry_failed=True)
        flat = flatten_episode(final)
        self.assertEqual(flat["status"], "success")
        self.assertEqual(flat["attempt_count"], 2)
        self.assertEqual(flat["failed_attempt_count"], 1)
        self.assertEqual(flat["input_tokens"], 8)
        self.assertEqual(flat["total_tokens"], 14)
        self.assertEqual(flat["reported_cost"], 0.02)
        self.assertEqual(flat["latest_attempt_costs"]["reported_cost"], 0.01)
        self.assertEqual(final["cumulative_usage"]["reported_cost"], 0.02)

    def test_missing_usage_is_unknown_while_zero_calls_is_zero(self):
        empty = usage_totals([])
        self.assertEqual(empty["prompt_tokens"], 0)
        self.assertEqual(empty["reported_cost"], 0)
        missing = usage_totals([{"type": "model_call", "usage": {}}])
        for key in ("prompt_tokens", "completion_tokens", "total_tokens", "reported_cost"):
            self.assertIsNone(missing[key])
        partial = usage_totals([
            {"type": "model_call", "usage": {"prompt_tokens": 7, "cost": 0.03}},
            {"type": "model_call", "usage": {"prompt_tokens": 5}},
        ])
        self.assertEqual(partial["prompt_tokens"], 12)
        self.assertIsNone(partial["completion_tokens"])
        self.assertIsNone(partial["reported_cost"])
        self.assertEqual(partial["reported_cost_partial"], 0.03)
        self.assertEqual(partial["calls_missing_reported_cost"], 1)
        self.assertFalse(partial["cost_is_complete"])

    def test_analysis_action_after_budget_fails_without_extra_tool_run(self):
        calls = []

        def transport(*_):
            calls.append(1)
            return response({"tool": "fit_model", "spec": {"kind": "linear"}})

        result = self.episode(transport, "adaptive", config=Config(max_steps=1))
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["failure"]["code"], "unknown_or_disallowed_tool")
        self.assertEqual(sum(e["type"] == "tool_result" for e in result["events"]), 1)
        self.assertEqual(self.score_calls, 0)

    def test_interruption_persists_failure_before_propagating(self):
        def transport(*_):
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            self.episode(transport)
        saved = json.loads(next(self.output.glob("*.json")).read_text())
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["failure"]["code"], "interrupted")
        self.assertEqual(self.score_calls, 0)

    def test_api_failures_never_log_exception_or_transport_output(self):
        sentinel = "private_api_secret"

        def transport(*_):
            print(sentinel)
            return {"status": "error", "error": sentinel, "usage": {"cost": 0.003, "secret": sentinel}}

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = self.episode(transport)
        self.assertEqual(result["failure"]["code"], "api_failure")
        self.assertNotIn(sentinel, output.getvalue())
        self.assertNotIn(sentinel, json.dumps(result))
        self.assertEqual(result["usage"]["reported_cost"], 0.003)

    def test_successful_resume_skips_session_and_model(self):
        self.episode(lambda *_: response(submit()))
        result = self.episode(lambda *_: self.fail("must not call model"),
                              session_factory=lambda *_args, **_kwargs: self.fail("must not fit"))
        self.assertEqual(result["status"], "success")
        self.assertEqual(self.score_calls, 1)

    def test_code_and_data_fingerprints_change_cache_keys(self):
        args = dict(seed=101, condition="null", workflow="fixed", fingerprint="data1", code_hash="code1")
        original = build_config_hash(Config(), **args)
        self.assertNotEqual(original, build_config_hash(Config(), **{**args, "code_hash": "code2"}))
        self.assertNotEqual(original, build_config_hash(Config(), **{**args, "fingerprint": "data2"}))
        self.assertNotEqual(original, build_config_hash(Config(model="other"), **args))

    def test_profiles_prompts_and_budgets_do_not_share_cached_results(self):
        args = dict(seed=301, condition="null", workflow="fixed", fingerprint="same", code_hash="same")
        hashes = {build_config_hash(profile_config(p, v), **args)
                  for p in ("gpt4.1", "sol_medium", "astra_medium") for v in ("P0", "P1")}
        self.assertEqual(len(hashes), 6)
        self.assertNotEqual(build_config_hash(Config(), **args),
                            build_config_hash(Config(max_completion_tokens=8192), **args))
        self.assertIsNone(transport_options(profile_config("astra_medium", "P0"))["temperature"])
        self.assertEqual(transport_options(profile_config("sol_medium", "P1"))["reasoning_effort"], "medium")

    def test_rules_only_change_system_prompt_not_fixed_evidence(self):
        prompts = []
        payloads = []
        def transport(_model, system, user, _round):
            prompts.append(system)
            payloads.append(json.loads(user))
            return response(submit())
        for variant in ("P0", "P1"):
            result = self.episode(transport, config=profile_config("gpt4.1", variant))
            self.assertEqual(result["status"], "success")
        self.assertEqual(payloads[0], payloads[1])
        self.assertEqual(prompts, [system_prompt("P0"), system_prompt("P1")])
        self.assertTrue(prompts[1].startswith(prompts[0]))

    def test_truncated_completion_keeps_metadata_usage_and_does_not_score(self):
        result = self.episode(lambda *_: response(submit(), actual_model="resolved-model",
            finish_reason="length", provider="provider", generation_id="gen-123",
            usage={"cost": 0.2, "completion_tokens": 8192,
                   "completion_tokens_details": {"reasoning_tokens": 8000}}))
        self.assertEqual(result["failure"]["code"], "completion_truncated")
        event = [e for e in result["events"] if e["type"] == "model_call"][0]
        self.assertEqual(event["reasoning_tokens"], 8000)
        self.assertEqual(event["finish_reason"], "length")
        self.assertEqual(result["actual_model"], "resolved-model")
        self.assertEqual(result["usage"]["reported_cost"], 0.2)
        self.assertEqual(self.score_calls, 0)

    def test_offline_reference_never_calls_model(self):
        result = self.episode(lambda *_: self.fail("offline API call"), "offline_reference",
                              config=Config(mode="offline_reference"))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["workflow"], "offline_reference")
        self.assertEqual(result["usage"]["model_calls"], 0)

    def test_default_dry_run_does_not_read_credentials(self):
        real_get = os.environ.get

        def guarded_get(key, *args):
            if key == "OPENROUTER_KEY":
                raise AssertionError("credential read")
            return real_get(key, *args)

        with patch("os.environ.get", side_effect=guarded_get):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main([]), 0)

    def test_missing_key_fails_before_dataset_or_cache(self):
        with patch.dict("os.environ", {}, clear=True):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--execute", "--output", str(self.output)]), 2)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_default_output_is_experiment_artifacts_directory(self):
        self.assertEqual(parser().parse_args([]).output, Path(__file__).resolve().parent / "artifacts")

    def test_cli_rejects_negative_or_duplicate_episode_axes(self):
        cases = [
            ["--seeds", "-1"], ["--seeds", "101", "101"],
            ["--conditions", "global", "global"],
            ["--workflows", "fixed", "fixed"],
        ]
        for args in cases:
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    main(args)
                self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
