"""
The whole loop and the scoring, with a scripted stand-in instead of a model. No API calls.
"""

import json

import pytest

import explore
from score import score


def test_scripted_episode_runs_end_to_end_and_scores():
    ep = explore.run_episode(seed=0, respond=explore.scripted(explore.SCRIPTED_REPLIES))
    assert [t.get("new_runs", 0) for t in ep["turns"]] == [100, 100, 0, 0]
    assert ep["turns"][1]["refused"] == ["Experiment 3: only 50 of 5000 runs carried out (per-turn or total limit)."]
    assert ep["turns"][3]["error"] == "no tags"
    assert ep["report_turn"] == 5 and ep["predictions"] == [0, 2, -3, 2.5, 0, 0, 0, 0, 2, 0, 0]
    s = score(ep)
    i = s["interaction"]
    assert i["collected"] and not i["tested"] and i["put_x4x5_in_a_fit_it_could_not_estimate"]
    assert s["interaction_questions_following_truth"] == "0/4"
    assert s["proxy_questions_following_truth"] == "2/2"
    assert s["design"]["runs_nothing_set"] == 150 and s["design"]["runs_X4_and_X5_both_set_nonzero"] == 0


def test_running_out_of_turns_asks_for_the_paper():
    replies = ['<experiments>[{"n": 10}]</experiments>'] * explore.MAX_TURNS + [
        "no tags here, just a paper", "<predictions>[1, 2]</predictions>"]
    ep = explore.run_episode(seed=1, respond=explore.scripted(replies))
    assert ep["report_turn"] is None and ep["report_without_tags"]
    assert explore.prompts.OUT_OF_TURNS.format(max_turns=explore.MAX_TURNS) in ep["messages"][-4]["content"]
    assert len(ep["rows"]) == 10 * explore.MAX_TURNS
    assert score(ep)["predictions"][2]["predicted"] is None


def test_a_failed_call_keeps_what_was_collected(tmp_path):
    replies = iter(['<experiments>[{"n": 10}]</experiments>', '<experiments>[{"n": 5}]</experiments>'])

    def respond(messages):
        return {"content": next(replies), "finish_reason": "stop", "usage": {"cost": 0.25}}

    with pytest.raises(explore.Stopped) as stop:
        explore.run_episode(seed=0, respond=respond)
    assert str(stop.value).startswith("StopIteration") and len(stop.value.state["turns"]) == 2
    path = tmp_path / "run1.partial.json"
    explore.save_partial(path, stop.value, seed=1)
    saved = json.loads(path.read_text())
    assert saved["seed"] == 1 and saved["cost"] == 0.5 and len(saved["rows"]) == 15
    assert not list(tmp_path.glob("run*[0-9].json"))


def test_request_settings_per_model():
    messages = [{"role": "system", "content": "rules"}, {"role": "user", "content": "data"}]
    old = explore.request_body("gpt-4.1", messages)
    assert old["temperature"] == 0.7 and old["max_tokens"] == 8000 and "reasoning" not in old
    assert old["messages"] == messages
    new = explore.request_body("claude-sonnet-5.5", messages)
    assert new["model"] == "anthropic/claude-sonnet-5.5" and new["max_tokens"] == 32000
    assert new["reasoning"] == {"effort": "medium"} and "temperature" not in new and "cache" not in new
    assert new["messages"][0] == messages[0] and messages[1]["content"] == "data"
    assert new["messages"][1] == {"role": "user", "content": [
        {"type": "text", "text": "data", "cache_control": {"type": "ephemeral"}}]}


def test_prompt_variants_differ_by_one_sentence():
    base = explore.opening_messages("base")[1]["content"]
    unlimited = explore.opening_messages("unlimited")[1]["content"]
    sentence = explore.prompts.UNLIMITED_ANALYSES
    assert sentence not in base and sentence in unlimited
    assert unlimited.replace(sentence + " ", "") == base


def test_python_variant_adds_one_paragraph_and_nothing_else():
    unlimited = explore.opening_messages("unlimited")[1]["content"]
    python = explore.opening_messages("python")[1]["content"]
    section = explore.prompts.PYTHON_SECTION.format(max_output=explore.sandbox.MAX_OUTPUT, timeout=explore.sandbox.TIMEOUT)
    assert section not in unlimited and section in python
    assert python.replace(section + "\n\n", "") == unlimited


def fake_run_code(code, columns, rows):
    return {"exit_code": 0, "timed_out": False, "output": f"rows={len(rows)} ran: {code}", "truncated": False, "seconds": 0.1}


def test_python_blocks_run_after_experiments_and_are_logged():
    replies = [
        '<experiments>[{"n": 10}]</experiments><python>print(1)</python>\n<python>\n```python\ny = df["X4"] * df["X5"]\n```\n</python>',
        "just notes",
        "<report>paper</report>",
        "<predictions>[0,0,0,0,0,0,0,0,0,0,0]</predictions>",
    ]
    ep = explore.run_episode(seed=0, respond=explore.scripted(replies), variant="python", run_code=fake_run_code)
    first = ep["turns"][0]["python"]
    assert [b["code"] for b in first] == ["print(1)", 'y = df["X4"] * df["X5"]']
    assert first[0]["output"].startswith("rows=10")  # code sees the runs from the same reply
    assert "<python_output>" in ep["messages"][3]["content"]
    assert ep["messages"][5]["content"].startswith(explore.prompts.NO_TAGS_PYTHON)
    py = score(ep)["interaction"]["python"]
    assert py["blocks"] == 2 and py["blocks_forming_x4_times_x5"] == 1 and py["tested"]


def test_python_tags_are_ignored_outside_the_python_variant():
    replies = ["<python>print(1)</python>", "<report>paper</report>", "<predictions>[]</predictions>"]
    ep = explore.run_episode(seed=0, respond=explore.scripted(replies), variant="unlimited", run_code=fake_run_code)
    assert "python" not in ep["turns"][0] and ep["turns"][0]["error"] == "no tags"
