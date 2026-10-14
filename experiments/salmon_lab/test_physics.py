"""
Offline checks on the physics lab: the motion matches closed-form results, the new law
does what it should and nothing else, requests are validated, the evidence check and the
law tests behave, and the loop and the scoring run end to end with a scripted stand-in.
"""

import contextlib
import io
import math

import numpy as np
import pandas as pd
import pytest

import physics_explore
import physics_prompts as P
import physics_world as pw
from physics_score import score

NEUTRAL = {"mass": 1.0, "radius": 0.05, "shape": "sphere", "reflectance": 0.5, "temperature": 20.0,
           "stripes": 0, "hardness": 5, "batch": 1}
VACUUM = {"height": 20.0, "speed": 0.0, "angle": 0.0, "air_density": 0.0}


def flight(obj, launch, kappa=pw.KAPPA):
    t, d, v = pw.simulate([obj], [launch], kappa)
    return float(t[0]), float(d[0]), float(v[0])


def test_vacuum_drop_and_throw_match_closed_forms():
    t, _, v = flight(NEUTRAL, VACUUM)
    assert t == pytest.approx(math.sqrt(2 * 20 / pw.G), abs=1e-5)
    assert v == pytest.approx(math.sqrt(2 * pw.G * 20), abs=1e-4)
    launch = {"height": 5.0, "speed": 12.0, "angle": 35.0, "air_density": 0.0}
    vy, vx = 12 * math.sin(math.radians(35)), 12 * math.cos(math.radians(35))
    expected = (vy + math.sqrt(vy**2 + 2 * pw.G * 5)) / pw.G
    t, d, _ = flight(NEUTRAL, launch)
    assert t == pytest.approx(expected, abs=1e-5) and d == pytest.approx(vx * expected, abs=1e-4)


def test_drag_gives_the_textbook_terminal_velocity():
    light = NEUTRAL | {"mass": 0.1, "radius": 0.2}
    _, _, v = flight(light, VACUUM | {"air_density": 1.2, "height": 40.0})
    area = math.pi * 0.2**2
    assert v == pytest.approx(math.sqrt(2 * 0.1 * pw.G / (1.2 * 0.47 * area)), rel=1e-3)


def test_new_law_needs_both_colour_and_temperature():
    base, _, _ = flight(NEUTRAL, VACUUM)
    for change in ({"reflectance": 0.0}, {"reflectance": 1.0}, {"temperature": 80.0}, {"temperature": -20.0}):
        assert flight(NEUTRAL | change, VACUUM)[0] == pytest.approx(base, abs=1e-9)
    hot_dark, _, _ = flight(NEUTRAL | {"temperature": 80.0, "reflectance": 0.0}, VACUUM)
    hot_white, _, _ = flight(NEUTRAL | {"temperature": 80.0, "reflectance": 1.0}, VACUUM)
    assert hot_dark == pytest.approx(math.sqrt(2 * 20 / (pw.G - pw.KAPPA)), abs=1e-5)
    assert hot_white == pytest.approx(math.sqrt(2 * 20 / (pw.G + pw.KAPPA)), abs=1e-5)


def test_irrelevant_properties_change_nothing():
    base = flight(NEUTRAL, VACUUM | {"air_density": 1.2})
    other = flight(NEUTRAL | {"stripes": 9, "hardness": 1, "batch": 50}, VACUUM | {"air_density": 1.2})
    assert other == pytest.approx(base, abs=1e-12)


def test_unset_properties_are_random_and_launch_defaults_apply():
    lab = pw.PhysicsLab(0, run_budget=1000, max_runs_per_turn=1000)
    rows, messages = lab.run_experiments([{"object": {"shape": "cube", "mass": 2}, "launch": {"height": 30}, "n": 200}])
    assert not messages and len(rows) == 200
    assert all(r["object"]["shape"] == "cube" and r["object"]["mass"] == 2.0 for r in rows)
    assert all(r["launch"] == pw.LAUNCH_DEFAULT | {"height": 30.0} for r in rows)
    for key, (low, high, _) in pw.CONTINUOUS.items():
        values = [r["object"][key] for r in rows]
        if key != "mass":
            assert low <= min(values) and max(values) <= high and np.std(values) > 0
    assert {r["object"]["stripes"] for r in rows} == set(range(0, 11))


def test_bad_requests_and_limits():
    lab = pw.PhysicsLab(0, run_budget=150, max_runs_per_turn=100)
    bad = [{"object": {"shape": "pyramid"}}, {"launch": {"height": 99}}, {"object": {"stripes": 2.5}},
           {"object": {"colour": 1}}, {"n": 0}, {"n": True}, {"fly": 1}, {"object": {"mass": "heavy"}}]
    rows, messages = lab.run_experiments(bad)
    assert rows == [] and len(messages) == len(bad)
    rows, messages = lab.run_experiments([{"n": 80}, {"n": 40}])
    assert len(rows) == 100 and any("only 20 of 40" in m for m in messages)
    rows, _ = lab.run_experiments([{"n": 100}])
    assert len(rows) == 50 and lab.runs_left() == 0
    assert lab.run_experiments({"n": 1}) == ([], ["Experiments must be a JSON array."])


def test_code_table_lists_every_run():
    lab = pw.PhysicsLab(0)
    lab.run_experiments([{"n": 3}, {"object": {"temperature": 70}, "launch": {"air_density": 0}, "n": 2}])
    columns, rows = lab.code_table()
    assert columns == pw.COLUMNS and len(rows) == 5
    assert rows[0][-1] == "" and rows[-1][-1] == "temperature=70; air_density=0"


def test_evidence_is_in_passive_data_and_absent_one_at_a_time():
    lab = pw.PhysicsLab(1)
    for _ in range(3):
        lab.run_experiments([{"n": 100}])
    assert pw.interaction_evidence(lab.rows)["identifiable"]
    lab = pw.PhysicsLab(2)
    specs = [{"object": NEUTRAL | {"reflectance": r}, "n": 50} for r in (0.0, 1.0)]
    specs += [{"object": NEUTRAL | {"temperature": t}, "n": 50} for t in (-20.0, 80.0)]
    lab.run_experiments(specs[:2])
    lab.run_experiments(specs[2:])
    assert not pw.interaction_evidence(lab.rows)["identifiable"]


def test_law_tests_come_in_pairs_that_differ_only_in_colour_and_temperature():
    cases = pw.law_tests()
    assert len(cases) == 40
    for strong, neutral in zip(cases[0::2], cases[1::2]):
        assert strong["strong"] and not neutral["strong"] and strong["launch"] == neutral["launch"]
        differ = {k for k in pw.OBJECT if strong["object"][k] != neutral["object"][k]}
        assert len(differ) == 1 and differ <= {"reflectance", "temperature"}
    truth, baseline = pw.law_truth(cases), pw.law_truth(cases, 0.0)
    assert np.allclose(truth[1::2], baseline[1::2]) and not np.allclose(truth[0::2], baseline[0::2])


def run_here(code, columns, rows):
    """Stand-in for the sandbox: runs trusted test code in this process."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(code, "<test>", "exec"), {"__name__": "__main__", "df": pd.DataFrame(rows, columns=columns)})
    return {"exit_code": 0, "timed_out": False, "output": out.getvalue(), "truncated": False, "seconds": 0.0}


TRUE_LAW = """
import sys
sys.path.insert(0, {path!r})
import physics_world as pw

def predict(obj, launch):
    print("noise from the law is ignored")
    t, d, v = pw.simulate([obj], [launch])
    return {{"flight_time": t[0], "distance": d[0], "impact_speed": v[0]}}
"""


def test_scripted_episode_runs_and_scores(tmp_path):
    law = TRUE_LAW.format(path=str(pw.__file__).rsplit("/", 1)[0])
    replies = [
        '<experiments>[{"n": 80}, {"object": {"temperature": 75, "reflectance": 0.05}, "n": 20}]</experiments>'
        '<python>print(df.groupby(["reflectance", "temperature"]).size().head())</python>',
        "<report>Hot dark objects fall more slowly: reflectance and temperature act together.</report>",
        f"<law>{law}</law>",
    ]
    ep = physics_explore.run_episode(0, physics_explore.scripted(replies), run_code=run_here)
    assert ep["turns"][0]["new_runs"] == 100 and ep["law_predictions"] is not None
    s = score(ep)
    assert s["collected"]["identifiable"] and s["code"]["tested"] and s["report_sentences"]
    assert s["law"]["captures_new_law"] and s["law"]["pairs_right"] == 20 and s["found"]
    assert s["design"]["runs_setting_both_away_from_neutral"] == 20


def test_conditions_change_only_the_error_sentence_or_the_law_strength():
    briefing = {c: physics_explore.opening_messages(v["measurement_error"]) for c, v in physics_explore.CONDITIONS.items()}
    assert briefing["kappa2"] == briefing["base"] and briefing["stated_error"][0] == briefing["base"][0]
    assert briefing["kappa2_stated_error"] == briefing["stated_error"] == briefing["kappa0_stated_error"]
    assert briefing["kappa0"] == briefing["base"] and physics_explore.CONDITIONS["kappa0"]["kappa"] == 0
    assert physics_explore.CONDITIONS["kappa2_stated_error"]["kappa"] == physics_explore.CONDITIONS["kappa2"]["kappa"]
    stated = briefing["base"][1]["content"].replace(P.ERROR_UNSTATED, physics_explore.STATED_ERROR)
    assert stated == briefing["stated_error"][1]["content"]
    assert "0.01 s for flight_time and 1% of the true value" in stated
    replies = ['<experiments>[{"n": 5}]</experiments>', "<report>paper</report>", "<law>def predict(obj, launch): pass</law>"]
    ep = physics_explore.run_episode(0, physics_explore.scripted(replies), "kappa2", run_code=run_here)
    assert ep["condition"] == "kappa2" and ep["kappa"] == 2.0


def test_without_the_new_law_a_law_that_has_it_counts_as_invented():
    usual = TRUE_LAW.format(path=str(pw.__file__).rsplit("/", 1)[0])
    plain = physics_explore.SCRIPTED_REPLIES[-1].split("<law>")[1].split("</law>")[0]
    invented = []
    for law in (usual, plain):
        replies = ['<experiments>[{"n": 20}]</experiments>', "<report>paper</report>", f"<law>{law}</law>"]
        s = score(physics_explore.run_episode(0, physics_explore.scripted(replies), "kappa0", run_code=run_here))
        assert not s["found"] and "pairs_right" not in s["law"]
        invented.append((s["invented"], s["law"]["pairs_with_invented_gap"]))
    assert invented == [(True, 20), (False, 0)]


def test_a_failed_call_keeps_what_was_collected():
    replies = iter(['<experiments>[{"n": 7}]</experiments>'])
    respond = lambda messages: {"content": next(replies), "finish_reason": "stop", "usage": None}
    with pytest.raises(physics_explore.Stopped) as stop:
        physics_explore.run_episode(0, respond, run_code=run_here)
    assert len(stop.value.state["rows"]) == 7 and len(stop.value.state["messages"]) == 4


def test_a_law_without_the_new_term_does_not_capture_it():
    replies = ['<experiments>[{"n": 50}]</experiments>', "<report>paper</report>",
               f"<law>{physics_explore.SCRIPTED_REPLIES[-1].split('<law>')[1].split('</law>')[0]}</law>"]
    ep = physics_explore.run_episode(0, physics_explore.scripted(replies), run_code=run_here)
    law = score(ep)["law"]
    assert law["ran"] and law["pairs_right"] == 0 and not law["captures_new_law"]
