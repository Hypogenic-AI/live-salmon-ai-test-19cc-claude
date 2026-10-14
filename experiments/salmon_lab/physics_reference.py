"""
Scripted ways of collecting data in the physics lab, under the same budget the model gets
(300 runs, at most 100 per turn), and how often the new law is detectable in what each
collects (physics_world.interaction_evidence). Used to set KAPPA. No API calls.

    uv run python experiments/salmon_lab/physics_reference.py            # at KAPPA, saves results
    uv run python experiments/salmon_lab/physics_reference.py 0.1 0.3    # compare strengths
"""

import json
import sys
from pathlib import Path

import numpy as np

import physics_world as pw
from reference import in_turns

HERE = Path(__file__).parent
SEEDS = range(100)
BUDGET = 300
DEFAULT_OBJECT = {"mass": 1.0, "radius": 0.05, "shape": "sphere", "reflectance": 0.5, "temperature": 20.0,
                  "stripes": 0, "hardness": 5, "batch": 1}
LEVELS = {"mass": (0.5, 5.0), "radius": (0.03, 0.15), "reflectance": (0.1, 0.9), "temperature": (0.0, 60.0),
          "stripes": (2, 8), "hardness": (2, 8), "batch": (10, 40)}


def observe(n):
    return lambda rng: [{"n": n}]


def one_at_a_time(rest_at_default):
    def specs(rng):
        return [{"object": (DEFAULT_OBJECT if rest_at_default else {}) | {prop: level}, "n": 20}
                for prop, levels in LEVELS.items() for level in levels]
    return specs


def random_everything(rng):
    specs = []
    for _ in range(BUDGET):
        obj = {k: round(float(rng.uniform(lo, hi)), d) for k, (lo, hi, d) in pw.CONTINUOUS.items()}
        launch = {k: round(float(rng.uniform(lo, hi)), 2) for k, (lo, hi) in pw.LAUNCH_RANGE.items()}
        specs.append({"object": obj, "launch": launch, "n": 1})
    return specs


STRATEGIES = {
    "observe only, 25 runs": observe(25),
    "observe only, 50 runs": observe(50),
    "observe only, 100 runs": observe(100),
    "observe only, 300 runs": observe(300),
    "one property at a time, rest at defaults (280 runs)": one_at_a_time(True),
    "one property at a time, rest random (280 runs)": one_at_a_time(False),
    "random objects and launches (300 runs)": random_everything,
}


def detection_rates(kappa):
    out = {}
    for name, make in STRATEGIES.items():
        hits = []
        for seed in SEEDS:
            lab = pw.PhysicsLab(seed, kappa=kappa)
            for turn in in_turns(make(np.random.default_rng(10_000 + seed))):
                _, messages = lab.run_experiments(turn)
                assert not messages, messages
            hits.append(pw.interaction_evidence(lab.rows)["identifiable"])
        out[name] = float(np.mean(hits))
    return out


def main():
    kappas = [float(k) for k in sys.argv[1:]] or [pw.KAPPA]
    table = {k: detection_rates(k) for k in kappas}
    print(f"{len(SEEDS)} simulated labs per strategy; share in which the new law is detectable\n")
    print(f"{'strategy':<55}" + "".join(f"{'kappa ' + format(k, 'g'):>12}" for k in kappas))
    for name in STRATEGIES:
        print(f"{name:<55}" + "".join(f"{table[k][name]:>12.0%}" for k in kappas))
    if kappas == [pw.KAPPA]:
        (HERE / "physics_reference_results.json").write_text(json.dumps(table[pw.KAPPA], indent=2))


if __name__ == "__main__":
    main()
