"""
Scripted ways of collecting data, under the same budget the AI gets (300 runs, at most
100 per turn), and whether the X4 X5 interaction is detectable in what each collects.

"Detectable" is world.interaction_evidence: fit all 20 main effects plus one product at
a time for all 190 pairs, and ask whether X4:X5 passes a Bonferroni threshold. This
shows the evidence is within reach of a simple strategy, and which ways of collecting
data destroy it. No API calls.

    uv run python experiments/salmon_lab/reference.py
"""

import json
from pathlib import Path

import numpy as np

from world import NAMES, LabWorld

HERE = Path(__file__).parent
SEEDS = range(200)
BUDGET, PER_TURN = 300, 100


def observe(n):
    return lambda rng: [{"n": n}]


def one_at_a_time(rest_at_zero):
    def specs(rng):
        out = []
        for v in NAMES:
            for level in (-2, 2):
                setting = {u: 0 for u in NAMES} if rest_at_zero else {}
                out.append({"set": setting | {v: level}, "n": 7})
        return out
    return specs


def random_settings(rng):
    return [{"set": {v: round(float(rng.uniform(-3, 3)), 2) for v in NAMES}, "n": 1} for _ in range(BUDGET)]


def observe_then_one_at_a_time(rng):
    return observe(100)(rng) + [{"set": {u: 0 for u in NAMES} | {v: level}, "n": 5}
                                 for v in NAMES for level in (-2, 2)]


STRATEGIES = {
    "observe only, 25 runs": observe(25),
    "observe only, 50 runs": observe(50),
    "observe only, 100 runs": observe(100),
    "observe only, 300 runs": observe(300),
    "one at a time, rest held at 0 (280 runs)": one_at_a_time(rest_at_zero=True),
    "one at a time, rest left natural (280 runs)": one_at_a_time(rest_at_zero=False),
    "random settings of all 20 (300 runs)": random_settings,
    "observe 100, then one at a time with rest at 0 (300 runs)": observe_then_one_at_a_time,
}


def in_turns(specs):
    """Split experiments into turns of at most PER_TURN runs, as the AI would have to."""
    turns, current, used = [], [], 0
    for spec in specs:
        n = spec["n"]
        while n > 0:
            take = min(n, PER_TURN - used)
            current.append(spec | {"n": take})
            used, n = used + take, n - take
            if used == PER_TURN:
                turns.append(current)
                current, used = [], 0
    return turns + ([current] if current else [])


def main():
    summary = {}
    for name, make in STRATEGIES.items():
        results = []
        for seed in SEEDS:
            world = LabWorld(seed, run_budget=BUDGET, max_runs_per_turn=PER_TURN)
            for turn in in_turns(make(np.random.default_rng(10_000 + seed))):
                _, messages = world.run_experiments(turn)
                assert not messages, messages
            results.append(world.evidence())
        estimable = [r for r in results if r["x4x5_estimable"]]
        summary[name] = {
            "runs": results[0]["n"],
            "share_detectable": np.mean([r["identifiable"] for r in results]),
            "share_estimable": len(estimable) / len(results),
            "median_t": float(np.median([r["x4x5_t"] for r in estimable])) if estimable else None,
            "median_rank_among_pairs": float(np.median([r["x4x5_rank"] for r in estimable])) if estimable else None,
            "mean_estimate": float(np.mean([r["x4x5_estimate"] for r in estimable])) if estimable else None,
        }
    print(f"{len(SEEDS)} simulated labs per strategy; true X4:X5 coefficient 0.8\n")
    print(f"{'strategy':<60}{'runs':>6}{'detectable':>12}{'median t':>10}{'rank':>6}{'estimate':>10}")
    for name, s in summary.items():
        fmt = lambda v, f: "—" if v is None else format(v, f)
        print(f"{name:<60}{s['runs']:>6}{s['share_detectable']:>12.0%}{fmt(s['median_t'], '.1f'):>10}"
              f"{fmt(s['median_rank_among_pairs'], '.0f'):>6}{fmt(s['mean_estimate'], '.2f'):>10}")
    (HERE / "reference_results.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
