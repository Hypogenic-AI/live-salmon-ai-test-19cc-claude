"""Runner behaviour with a mocked transport.  No network."""
import json

import pytest

from infocond import runner
from infocond.paths import EXP_DIR


def _ok_body(content="# Paper\n\nWe find nothing.", finish="stop", model="openai/gpt-4.1"):
    return {"id": "gen-1", "model": model, "provider": "OpenAI", "created": 1,
            "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish, "native_finish_reason": finish}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


def _plan(bundles, phase="smoke", rep=1):
    b = bundles[0]
    return {"phase": phase, "dataset": b["dataset"], "condition": b["condition"], "rep": rep, "cache_key": "deadbeef00000000",
            "record_file": "x.json", "prompt_hash": b["hashes"]["combined_sha256"], "model_key": "gpt-4.1",
            "model_id": "openai/gpt-4.1", "system_prompt": b["system_prompt"], "user_prompt": b["user_prompt"], "schedule_index": 0}


class Transport:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def __call__(self, url, payload, headers, timeout):
        self.calls.append(payload)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_success_first_attempt_records_everything(cfg, bundles):
    t = Transport([(200, _ok_body())])
    rec = runner.execute_call(_plan(bundles), cfg, "k", post_fn=t, sleep_fn=lambda s: None)
    assert rec["status"] == "success" and rec["n_attempts"] == 1 and rec["truncated"] is False
    assert rec["requested_model"] == "openai/gpt-4.1" and rec["response_model"] == "openai/gpt-4.1" and rec["model_mismatch"] is False
    assert rec["content"].startswith("# Paper") and rec["usage"]["total_tokens"] == 15 and rec["provider"] == "OpenAI"
    assert rec["raw_response"]["id"] == "gen-1" and rec["attempts"][0]["outcome"] == "success"
    assert rec["request_settings"] == cfg["request_settings"] and rec["started_at"] and rec["finished_at"]
    payload = t.calls[0]
    assert payload["temperature"] == 0.7 and payload["max_tokens"] == 4096 and "seed" not in payload
    assert payload["messages"][0]["role"] == "system" and payload["messages"][1]["content"] == bundles[0]["user_prompt"]


def test_transient_then_success(cfg, bundles):
    sleeps = []
    t = Transport([runner.TransientFailure("ConnectTimeout"), (429, {"error": "rate"}), (200, _ok_body())])
    rec = runner.execute_call(_plan(bundles), cfg, "k", post_fn=t, sleep_fn=sleeps.append)
    assert rec["status"] == "success" and rec["n_attempts"] == 3
    assert [a["outcome"] for a in rec["attempts"]] == ["transient_error", "transient_error", "success"]
    assert sleeps == [2.0, 4.0]


def test_bounded_retries_then_failure(cfg, bundles):
    t = Transport([(503, "down")] * 10)
    rec = runner.execute_call(_plan(bundles), cfg, "k", post_fn=t, sleep_fn=lambda s: None)
    assert rec["status"] == "failed" and rec["n_attempts"] == cfg["retry"]["max_attempts"] == 3
    assert len(t.calls) == 3 and rec["content"] is None
    assert all(a["http_status"] == 503 for a in rec["attempts"])


def test_permanent_failure_not_retried(cfg, bundles):
    t = Transport([(401, {"error": "bad key"})] + [(200, _ok_body())] * 3)
    rec = runner.execute_call(_plan(bundles), cfg, "k", post_fn=t, sleep_fn=lambda s: None)
    assert rec["status"] == "failed" and rec["n_attempts"] == 1 and len(t.calls) == 1
    assert rec["attempts"][0]["outcome"] == "permanent_error"


def test_malformed_and_empty_bodies_are_technical_failures(cfg, bundles):
    t = Transport([(200, {"choices": []}), (200, {"choices": [{"message": {"content": "   "}}]}), (200, _ok_body())])
    rec = runner.execute_call(_plan(bundles), cfg, "k", post_fn=t, sleep_fn=lambda s: None)
    assert rec["status"] == "success" and rec["n_attempts"] == 3


def test_truncation_flagged_not_retried(cfg, bundles):
    t = Transport([(200, _ok_body(content="# Paper cut off", finish="length"))] + [(200, _ok_body())])
    rec = runner.execute_call(_plan(bundles), cfg, "k", post_fn=t, sleep_fn=lambda s: None)
    assert rec["status"] == "success" and rec["truncated"] is True and len(t.calls) == 1
    assert rec["content"] == "# Paper cut off"


def test_unfavourable_or_odd_content_is_never_retried(cfg, bundles):
    for content in ("No significant relationships were found.", "We detect X4*X5.", "garbage ??? %%%", "0"):
        t = Transport([(200, _ok_body(content=content))] + [(200, _ok_body())])
        rec = runner.execute_call(_plan(bundles), cfg, "k", post_fn=t, sleep_fn=lambda s: None)
        assert rec["status"] == "success" and len(t.calls) == 1 and rec["content"] == content


# ---------------------------------------------------------------------------
# Explicit refusals: a third terminal outcome, never retried, never scored
# ---------------------------------------------------------------------------

def _refusal_body(refusal="I can't help with that request.", content=None, finish="stop", native=None):
    """A structured refusal: message.refusal set, content typically null."""
    msg = {"role": "assistant", "content": content}
    if refusal is not None:
        msg["refusal"] = refusal
    return {"id": "gen-refused", "model": "openai/gpt-4.1", "provider": "OpenAI", "created": 7,
            "choices": [{"message": msg, "finish_reason": finish, "native_finish_reason": native or finish}],
            "usage": {"prompt_tokens": 7479, "completion_tokens": 12, "total_tokens": 7491}}


def test_structured_refusal_is_terminal_and_fully_recorded(cfg, bundles):
    """One call, no retry, and every response field kept for inspection."""
    t = Transport([(200, _refusal_body())] + [(200, _ok_body())] * 3)
    rec = runner.execute_call(_plan(bundles), cfg, "k", post_fn=t, sleep_fn=lambda s: None)

    assert len(t.calls) == 1, "a refusal must not be re-rolled"
    assert rec["n_attempts"] == 1 and [a["outcome"] for a in rec["attempts"]] == ["refusal"]
    # a third status, distinct from both success and failure
    assert rec["status"] == "refused"
    assert rec["status"] not in ("success", "failed")
    # preserved: refusal text, finish reason, usage, raw response, model strings
    assert rec["refusal"] == "I can't help with that request."
    assert rec["refusal_reason"] == "message.refusal"
    assert rec["finish_reason"] == "stop" and rec["native_finish_reason"] == "stop"
    assert rec["usage"] == {"prompt_tokens": 7479, "completion_tokens": 12, "total_tokens": 7491}
    assert rec["raw_response"]["id"] == "gen-refused" and rec["response_id"] == "gen-refused"
    assert rec["response_model"] == "openai/gpt-4.1" and rec["provider"] == "OpenAI"
    assert rec["model_mismatch"] is False and rec["truncated"] is False
    # content was null and stays null: nothing is invented to fill the gap
    assert rec["content"] is None


def test_refusal_with_content_null_is_not_treated_as_malformed(cfg, bundles):
    """The regression this guards: `content: null` + refusal used to look like a
    missing field and burned three attempts as a technical failure."""
    t = Transport([(200, _refusal_body(content=None))] * 3)
    rec = runner.execute_call(_plan(bundles), cfg, "k", post_fn=t, sleep_fn=lambda s: None)
    assert len(t.calls) == 1 and rec["status"] == "refused"
    assert rec["attempts"][0]["error_type"] == "ContentRefusal"


@pytest.mark.parametrize("finish,native", [("content_filter", "content_filter"), ("stop", "SAFETY"),
                                           ("stop", "PROHIBITED_CONTENT")])
def test_content_filter_finish_reason_is_terminal(cfg, bundles, finish, native):
    body = _refusal_body(refusal=None, content=None, finish=finish, native=native)
    t = Transport([(200, body)] + [(200, _ok_body())] * 3)
    rec = runner.execute_call(_plan(bundles), cfg, "k", post_fn=t, sleep_fn=lambda s: None)
    assert len(t.calls) == 1 and rec["status"] == "refused"
    assert rec["refusal_reason"].startswith(("finish_reason=", "native_finish_reason="))
    assert rec["raw_response"] is body and rec["usage"]["total_tokens"] == 7491


def test_content_filter_keeps_any_partial_content_but_does_not_score_it(cfg, bundles):
    t = Transport([(200, _refusal_body(refusal=None, content="# Partial", finish="content_filter"))])
    rec = runner.execute_call(_plan(bundles), cfg, "k", post_fn=t, sleep_fn=lambda s: None)
    assert rec["status"] == "refused" and rec["content"] == "# Partial"


def test_malformed_responses_still_get_bounded_retries(cfg, bundles):
    """The refusal path must not swallow genuinely malformed or empty responses."""
    for body in ({"choices": [{"message": {}}]},                       # content missing
                 {"choices": [{"message": {"content": None}}]},        # null content, no refusal
                 {"choices": [{"message": {"content": "  "}}]},        # whitespace only
                 {"choices": []}):
        t = Transport([(200, body)] * 5)
        rec = runner.execute_call(_plan(bundles), cfg, "k", post_fn=t, sleep_fn=lambda s: None)
        assert rec["status"] == "failed" and len(t.calls) == 3, body
        assert all(a["outcome"] == "transient_error" for a in rec["attempts"])
    # an empty refusal string is not a refusal
    t = Transport([(200, _refusal_body(refusal="   ", content=None))] * 5)
    rec = runner.execute_call(_plan(bundles), cfg, "k", post_fn=t, sleep_fn=lambda s: None)
    assert rec["status"] == "failed" and len(t.calls) == 3


@pytest.mark.parametrize("body", [{"choices": [42]},
                                  {"choices": ["x"]},
                                  {"choices": [{"message": "oops"}]},
                                  {"choices": [{"message": 7}]}])
def test_structurally_wrong_types_are_transient_not_a_crash(cfg, bundles, body):
    """These used to raise AttributeError out of the retry loop, so the call never
    reached the bounded-retry path and no failed record was written."""
    t = Transport([(200, body)] * 5)
    rec = runner.execute_call(_plan(bundles), cfg, "k", post_fn=t, sleep_fn=lambda s: None)
    assert rec["status"] == "failed" and len(t.calls) == 3
    assert all(a["outcome"] == "transient_error" for a in rec["attempts"])


def test_phase_summary_counts_refusals_separately_and_retry_failed_does_not_reroll(cfg, bundles, tmp_path):
    t = Transport([(200, _refusal_body())] + [(200, _ok_body())] * 5)
    s = runner.run_phase("smoke", cfg, bundles, execute=True, runs_dir=tmp_path, api_key="k", post_fn=t,
                         sleep_fn=lambda s: None, pause_between_calls=0, log=lambda m: None)
    assert len(t.calls) == 6
    assert (s["planned"], s["called"], s["success"], s["refused"], s["failed"]) == (6, 6, 5, 1, 0)
    assert len(s["refusals"]) == 1
    ref = s["refusals"][0]
    assert ref["refusal_reason"] == "message.refusal"
    assert ref["refusal"] == "I can't help with that request."
    assert ref["usage"]["total_tokens"] == 7491 and ref["finish_reason"] == "stop"
    assert [r for r in s["records"] if r["state"] == "refused"][0]["refusal_reason"] == "message.refusal"

    # rerun: the refusal is cached, counted, and not called again
    t2 = Transport([])
    s2 = runner.run_phase("smoke", cfg, bundles, execute=True, runs_dir=tmp_path, api_key="k", post_fn=t2,
                          sleep_fn=lambda s: None, pause_between_calls=0, log=lambda m: None)
    assert t2.calls == [] and s2["called"] == 0
    assert (s2["success"], s2["refused"], s2["failed"]) == (5, 1, 0)
    assert s2["already_cached_success"] == 5 and s2["already_cached_refused"] == 1

    # --retry-failed is for technical failures only: it must not re-roll a refusal
    t3 = Transport([])
    s3 = runner.run_phase("smoke", cfg, bundles, execute=True, runs_dir=tmp_path, api_key="k", post_fn=t3,
                          sleep_fn=lambda s: None, pause_between_calls=0, retry_failed=True, log=lambda m: None)
    assert t3.calls == [], "--retry-failed must not re-call a refused record"
    assert s3["called"] == 0 and s3["refused"] == 1 and s3["already_cached_refused"] == 1

    # the record on disk still holds everything
    refused = [json.loads(p.read_text()) for p in (tmp_path / "smoke" / "records").glob("*.json")]
    refused = [r for r in refused if r["status"] == "refused"]
    assert len(refused) == 1 and refused[0]["raw_response"]["id"] == "gen-refused"
    assert refused[0]["n_attempts"] == 1


def test_model_mismatch_is_flagged_not_substituted(cfg, bundles):
    t = Transport([(200, _ok_body(model="openai/gpt-4.1-2025-04-14"))])
    rec = runner.execute_call(_plan(bundles), cfg, "k", post_fn=t, sleep_fn=lambda s: None)
    assert rec["status"] == "success" and rec["model_mismatch"] is True
    assert rec["requested_model"] == "openai/gpt-4.1" and rec["response_model"] == "openai/gpt-4.1-2025-04-14"


def test_seed_only_sent_when_configured(cfg, bundles):
    p = _plan(bundles)
    assert "seed" not in runner.build_payload(p, cfg)
    cfg2 = {**cfg, "request_settings": {**cfg["request_settings"], "seed": 7}}
    assert runner.build_payload(p, cfg2)["seed"] == 7


def test_run_phase_dry_run_makes_no_calls_and_writes_plan(cfg, bundles, tmp_path):
    t = Transport([])
    s = runner.run_phase("smoke", cfg, bundles, execute=False, runs_dir=tmp_path, post_fn=t, sleep_fn=lambda s: None)
    assert s["planned"] == 6 and s["called"] == 0 and t.calls == []
    assert (tmp_path / "smoke" / "schedule.json").exists() and (tmp_path / "smoke" / "dry_run_plan.json").exists()
    assert not list((tmp_path / "smoke" / "records").glob("*.json"))
    f = runner.run_phase("formal", cfg, bundles, execute=False, runs_dir=tmp_path, post_fn=t, sleep_fn=lambda s: None)
    assert f["planned"] == 30


def test_run_phase_execute_caches_and_never_reuses_smoke_for_formal(cfg, bundles, tmp_path):
    t = Transport([(200, _ok_body())] * 6)
    s = runner.run_phase("smoke", cfg, bundles, execute=True, runs_dir=tmp_path, api_key="k", post_fn=t,
                         sleep_fn=lambda s: None, pause_between_calls=0, log=lambda m: None)
    assert s["called"] == 6 and s["success"] == 6 and len(t.calls) == 6
    recs = sorted((tmp_path / "smoke" / "records").glob("*.json"))
    assert len(recs) == 6 and all(p.name.startswith("smoke__") for p in recs)
    # second smoke invocation: everything cached, no calls
    t2 = Transport([])
    s2 = runner.run_phase("smoke", cfg, bundles, execute=True, runs_dir=tmp_path, api_key="k", post_fn=t2,
                          sleep_fn=lambda s: None, pause_between_calls=0, log=lambda m: None)
    assert s2["called"] == 0 and s2["already_cached_success"] == 6 and t2.calls == []
    # formal phase does not see smoke records: all 30 calls are made
    t3 = Transport([(200, _ok_body())] * 30)
    f = runner.run_phase("formal", cfg, bundles, execute=True, runs_dir=tmp_path, api_key="k", post_fn=t3,
                         sleep_fn=lambda s: None, pause_between_calls=0, log=lambda m: None)
    assert f["called"] == 30 and len(t3.calls) == 30
    frecs = list((tmp_path / "formal" / "records").glob("*.json"))
    assert len(frecs) == 30 and all(p.name.startswith("formal__") for p in frecs)
    keys_s = {json.loads(p.read_text())["cache_key"] for p in recs}
    keys_f = {json.loads(p.read_text())["cache_key"] for p in frecs}
    assert not (keys_s & keys_f)


def test_failed_records_skipped_unless_retry_failed(cfg, bundles, tmp_path):
    t = Transport([(500, "x")] * 3 + [(200, _ok_body())] * 5)
    s = runner.run_phase("smoke", cfg, bundles, execute=True, runs_dir=tmp_path, api_key="k", post_fn=t,
                         sleep_fn=lambda s: None, pause_between_calls=0, log=lambda m: None)
    assert s["failed"] == 1 and s["success"] == 5
    t2 = Transport([(200, _ok_body())])
    s2 = runner.run_phase("smoke", cfg, bundles, execute=True, runs_dir=tmp_path, api_key="k", post_fn=t2,
                          sleep_fn=lambda s: None, pause_between_calls=0, log=lambda m: None)
    assert s2["skipped_failed"] == 1 and t2.calls == []
    s3 = runner.run_phase("smoke", cfg, bundles, execute=True, runs_dir=tmp_path, api_key="k", post_fn=t2,
                          sleep_fn=lambda s: None, pause_between_calls=0, retry_failed=True, log=lambda m: None)
    assert s3["called"] == 1 and s3["failed"] == 0 and s3["success"] == 6
    rec = next(json.loads(p.read_text()) for p in (tmp_path / "smoke" / "records").glob("*.json") if json.loads(p.read_text()).get("previous_attempts"))
    assert len(rec["previous_attempts"]) == 3 and rec["status"] == "success"


def test_execute_requires_api_key(cfg, bundles, tmp_path):
    with pytest.raises(RuntimeError):
        runner.run_phase("smoke", cfg, bundles, execute=True, runs_dir=tmp_path, api_key="", post_fn=Transport([]),
                         sleep_fn=lambda s: None, pause_between_calls=0, log=lambda m: None)


def test_preflight_refuses_a_model_other_than_the_frozen_one(cfg, bundles, tmp_path):
    """--model must not be able to spend money on a model the freeze does not describe."""
    with pytest.raises(RuntimeError) as exc:
        runner.execution_preflight("smoke", cfg, bundles, "k", exp_dir=EXP_DIR,
                                   freezes_dir=tmp_path / "nofreezes", model_key="gemini-2.5-pro")
    msg = str(exc.value)
    assert "differs from the frozen config.json model_key" in msg and "gemini-2.5-pro" in msg


def test_preflight_reports_an_environment_mismatch(cfg, bundles, tmp_path):
    bad = {**cfg, "environment": {"python_minor": "3.13", "required_packages": {"pandas": "0.0.0"}}}
    with pytest.raises(RuntimeError) as exc:
        runner.execution_preflight("smoke", bad, bundles, "k", exp_dir=EXP_DIR, freezes_dir=tmp_path / "nofreezes")
    assert "environment: pandas" in str(exc.value)


def test_dry_run_cannot_overwrite_an_executed_schedule(cfg, bundles, tmp_path):
    """A preview with different arguments must not destroy the record of what ran."""
    t = Transport([(200, _ok_body())] * 6)
    runner.run_phase("smoke", cfg, bundles, execute=True, runs_dir=tmp_path, api_key="k", post_fn=t,
                     sleep_fn=lambda s: None, pause_between_calls=0, log=lambda m: None)
    sched = json.loads((tmp_path / "smoke" / "schedule.json").read_text())
    assert sched["model_id"] == "openai/gpt-4.1"
    with pytest.raises(RuntimeError) as exc:
        runner.run_phase("smoke", cfg, bundles, execute=False, runs_dir=tmp_path, model_key="gemini-2.5-pro",
                         post_fn=Transport([]), sleep_fn=lambda s: None, log=lambda m: None)
    assert "already been executed" in str(exc.value)
    after = json.loads((tmp_path / "smoke" / "schedule.json").read_text())
    assert after == sched, "the executed schedule must be untouched"
    # an identical re-run is still fine
    runner.run_phase("smoke", cfg, bundles, execute=False, runs_dir=tmp_path, post_fn=Transport([]),
                     sleep_fn=lambda s: None, log=lambda m: None)
    assert json.loads((tmp_path / "smoke" / "schedule.json").read_text()) == sched


def test_record_writes_are_atomic(cfg, bundles, tmp_path, monkeypatch):
    """An interrupted write must leave the previous record, not an unparseable one."""
    from infocond import common
    t = Transport([(200, _ok_body())] * 6)
    runner.run_phase("smoke", cfg, bundles, execute=True, runs_dir=tmp_path, api_key="k", post_fn=t,
                     sleep_fn=lambda s: None, pause_between_calls=0, log=lambda m: None)
    victim = sorted((tmp_path / "smoke" / "records").glob("*.json"))[0]
    before = victim.read_text()

    real_replace = common.os.replace

    def die(src, dst):                       # crash after the temp file is written, before the rename
        raise KeyboardInterrupt("interrupted")

    monkeypatch.setattr(common.os, "replace", die)
    with pytest.raises(KeyboardInterrupt):
        common.write_json(victim, {"half": "written"})
    monkeypatch.setattr(common.os, "replace", real_replace)
    assert victim.read_text() == before, "the previous record must survive an interrupted write"
    assert json.loads(victim.read_text())["status"] == "success"
    assert not list(victim.parent.glob("*.tmp")), "no temp file left behind"


def test_preflight_blocks_without_freeze(cfg, bundles, tmp_path):
    with pytest.raises(RuntimeError) as exc:
        runner.execution_preflight("smoke", cfg, bundles, "k", exp_dir=EXP_DIR, freezes_dir=tmp_path / "nofreezes")
    assert "no freeze record" in str(exc.value)
    with pytest.raises(RuntimeError) as exc2:
        runner.execution_preflight("smoke", cfg, bundles, "", exp_dir=EXP_DIR, freezes_dir=tmp_path / "nofreezes")
    assert "OPENROUTER_KEY" in str(exc2.value)


def test_preflight_refuses_when_upstream_remaps_the_model_key(cfg, bundles, tmp_path, monkeypatch):
    """The short key resolves through src/run_ai_scientists.py::MODELS, which is outside the
    experiment directory and so outside DESIGN_GLOBS.  Checking only the key would let an
    upstream remap send a different model while every key-level check still passed."""
    from infocond import freeze as F, upstream as U
    import json
    from infocond.paths import INPUTS_DIR
    frozen = {"freeze_file": "f.json", "design_hash": "d" * 64, "git_head": "h" * 40,
              "created_at": "t", "note": "n"}
    monkeypatch.setattr(F, "verify_freeze", lambda *a, **k: (True, "ok", frozen))

    frozen_id = json.loads((INPUTS_DIR / "manifest.json").read_text())["model"]["id"]
    runner.execution_preflight("formal", cfg, bundles, "k", model_key="gpt-4.1")   # baseline passes

    monkeypatch.setattr(U, "upstream_models", lambda: {"gpt-4.1": "openai/gpt-4o-mini"})
    with pytest.raises(RuntimeError) as exc:
        runner.execution_preflight("formal", cfg, bundles, "k", model_key="gpt-4.1")
    msg = str(exc.value)
    assert "openai/gpt-4o-mini" in msg and frozen_id in msg and "outside the design hash" in msg

    monkeypatch.setattr(U, "upstream_models", lambda: {"claude-sonnet-4.5": "anthropic/claude-sonnet-4.5"})
    with pytest.raises(RuntimeError) as exc2:
        runner.execution_preflight("formal", cfg, bundles, "k", model_key="gpt-4.1")
    assert "no longer in the upstream MODELS table" in str(exc2.value)

