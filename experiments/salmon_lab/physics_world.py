"""
A laboratory where objects are dropped or thrown and their flight is measured.

Gravity and quadratic air drag work as in the real world. One law does not exist in the
real world: an object feels an extra vertical acceleration

    a = kappa * (temperature - 20) / 60 * (0.5 - reflectance) / 0.5

so colour alone and temperature alone have no effect, and the effect vanishes at room
temperature or for a mid-grey object. Stripes, hardness and batch never matter.
"""

import itertools
import json
import math

import numpy as np
from scipy import stats

from world import RANK_TOL, _basis

G = 9.81
ROOM_TEMPERATURE = 20.0
KAPPA = 0.3
DT = 2e-3
MAX_TIME = 60.0

SHAPES = ("sphere", "cube", "cylinder")
DRAG_COEFFICIENT = {"sphere": 0.47, "cube": 1.05, "cylinder": 0.82}
CONTINUOUS = {"mass": (0.1, 10.0, 2), "radius": (0.02, 0.2, 3), "reflectance": (0.0, 1.0, 2), "temperature": (-20.0, 80.0, 1)}
INTEGER = {"stripes": (0, 10), "hardness": (1, 10), "batch": (1, 50)}
OBJECT = ["mass", "radius", "shape", "reflectance", "temperature", "stripes", "hardness", "batch"]
LAUNCH_RANGE = {"height": (0.5, 50.0), "speed": (0.0, 20.0), "angle": (-90.0, 90.0), "air_density": (0.0, 2.4)}
LAUNCH_DEFAULT = {"height": 10.0, "speed": 0.0, "angle": 0.0, "air_density": 1.2}
LAUNCH = list(LAUNCH_RANGE)
MEASURED = ["flight_time", "distance", "impact_speed"]
COLUMNS = ["run", *OBJECT, *LAUNCH, *MEASURED, "set"]
NUMERIC = [p for p in OBJECT if p != "shape"]
TIME_NOISE = 0.01  # seconds
RELATIVE_NOISE = 0.01


def extra_acceleration(reflectance, temperature, kappa=KAPPA):
    return kappa * (temperature - ROOM_TEMPERATURE) / 60.0 * (0.5 - reflectance) / 0.5


def frontal_area(shape, radius):
    return np.where(np.asarray(shape) == "cube", 4.0, math.pi) * np.asarray(radius) ** 2


def simulate(objects, launches, kappa=KAPPA):
    """Noise-free flight time, horizontal distance and impact speed for lists of objects and launches."""
    if not objects:
        return np.zeros(0), np.zeros(0), np.zeros(0)
    col = lambda dicts, key: np.array([d[key] for d in dicts], dtype=float)
    mass, radius = col(objects, "mass"), col(objects, "radius")
    shape = np.array([o["shape"] for o in objects])
    cd = np.array([DRAG_COEFFICIENT[s] for s in shape])
    k = 0.5 * col(launches, "air_density") * cd * frontal_area(shape, radius) / mass
    ay0 = -G + extra_acceleration(col(objects, "reflectance"), col(objects, "temperature"), kappa)
    angle = np.radians(col(launches, "angle"))
    speed = col(launches, "speed")
    state = np.stack([np.zeros_like(mass), col(launches, "height"), speed * np.cos(angle), speed * np.sin(angle)])

    def rate(s, k, ay):
        v = np.hypot(s[2], s[3])
        return np.stack([s[2], s[3], -k * v * s[2], ay - k * v * s[3]])

    n = len(objects)
    time_, distance, impact = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    active = np.ones(n, dtype=bool)
    t = 0.0
    while active.any() and t < MAX_TIME:
        s, ka, aya = state[:, active], k[active], ay0[active]
        k1 = rate(s, ka, aya)
        k2 = rate(s + DT / 2 * k1, ka, aya)
        k3 = rate(s + DT / 2 * k2, ka, aya)
        k4 = rate(s + DT * k3, ka, aya)
        new = s + DT / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        landed = new[1] <= 0
        if landed.any():
            idx = np.flatnonzero(active)[landed]
            frac = s[1, landed] / (s[1, landed] - new[1, landed])
            at = s[:, landed] + frac * (new[:, landed] - s[:, landed])
            time_[idx] = t + frac * DT
            distance[idx] = at[0]
            impact[idx] = np.hypot(at[2], at[3])
        state[:, active] = new
        active[np.flatnonzero(active)[landed]] = False
        t += DT
    return time_, distance, impact


def check(spec):
    """Validate one experiment. Returns (object settings, launch settings, n) or raises ValueError."""
    if not isinstance(spec, dict) or set(spec) - {"object", "launch", "n"}:
        raise ValueError('use {"object": {...}, "launch": {...}, "n": ...}')
    obj, launch, n = spec.get("object") or {}, spec.get("launch") or {}, spec.get("n", 1)
    if not isinstance(obj, dict) or not isinstance(launch, dict):
        raise ValueError('"object" and "launch" must map names to values')
    unknown = [k for k in obj if k not in OBJECT] + [k for k in launch if k not in LAUNCH]
    if unknown:
        raise ValueError(f"unknown name(s) {unknown}")
    number = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    for key, value in obj.items():
        if key == "shape":
            if value not in SHAPES:
                raise ValueError(f"shape must be one of {list(SHAPES)}")
        elif key in INTEGER:
            low, high = INTEGER[key]
            if not number(value) or value != int(value) or not low <= value <= high:
                raise ValueError(f"{key} must be a whole number from {low} to {high}")
        else:
            low, high, _ = CONTINUOUS[key]
            if not number(value) or not low <= value <= high:
                raise ValueError(f"{key} must be a number from {low:g} to {high:g}")
    for key, value in launch.items():
        low, high = LAUNCH_RANGE[key]
        if not number(value) or not low <= value <= high:
            raise ValueError(f"{key} must be a number from {low:g} to {high:g}")
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError('"n" must be a positive whole number')
    obj = {k: (v if k == "shape" else int(v) if k in INTEGER else float(v)) for k, v in obj.items()}
    return obj, {k: float(v) for k, v in launch.items()}, n


def describe(setting):
    parts = [f"{k} = {v:g}" if not isinstance(v, str) else f"{k} = {v}" for part in ("object", "launch")
             for k, v in setting[part].items()]
    return ", ".join(parts) if parts else "random object, default launch"


class PhysicsLab:
    def __init__(self, seed, kappa=KAPPA, run_budget=300, max_runs_per_turn=100):
        self.rng = np.random.default_rng(seed)
        self.kappa = kappa
        self.run_budget = run_budget
        self.max_runs_per_turn = max_runs_per_turn
        self.rows = []

    def runs_left(self):
        return self.run_budget - len(self.rows)

    def random_object(self):
        obj = {k: round(float(self.rng.uniform(low, high)), digits) for k, (low, high, digits) in CONTINUOUS.items()}
        obj["shape"] = str(self.rng.choice(SHAPES))
        obj.update({k: int(self.rng.integers(low, high + 1)) for k, (low, high) in INTEGER.items()})
        return {k: obj[k] for k in OBJECT}

    def run_experiments(self, specs):
        """Carry out a turn's experiments. Returns (new rows, messages about anything refused)."""
        if not isinstance(specs, list):
            return [], ["Experiments must be a JSON array."]
        planned, messages, this_turn = [], [], 0
        for k, spec in enumerate(specs, 1):
            try:
                obj, launch, n = check(spec)
            except ValueError as err:
                messages.append(f"Experiment {k} skipped: {err}.")
                continue
            allowed = min(n, self.max_runs_per_turn - this_turn, self.runs_left() - this_turn)
            if allowed < n:
                messages.append(f"Experiment {k}: only {allowed} of {n} runs carried out (per-turn or total limit).")
            for _ in range(allowed):
                planned.append(({"object": obj, "launch": launch}, self.random_object() | obj, LAUNCH_DEFAULT | launch))
            this_turn += allowed
            if allowed == 0:
                break
        times, distances, impacts = simulate([p[1] for p in planned], [p[2] for p in planned], self.kappa)
        new = []
        for (setting, obj, launch), t, d, v in zip(planned, times, distances, impacts):
            row = {
                "run": len(self.rows) + 1,
                "set": setting,
                "object": obj,
                "launch": launch,
                "flight_time": round(float(t) + float(self.rng.normal(0, TIME_NOISE)), 3),
                "distance": round(float(d) * (1 + float(self.rng.normal(0, RELATIVE_NOISE))), 2) + 0.0,
                "impact_speed": round(float(v) * (1 + float(self.rng.normal(0, RELATIVE_NOISE))), 2),
            }
            self.rows.append(row)
            new.append(row)
        return new, messages

    def code_table(self):
        """Columns and rows of the CSV that model-written code sees as `df`."""
        set_text = lambda s: "; ".join(f"{k}={v:g}" if not isinstance(v, str) else f"{k}={v}"
                                       for part in ("object", "launch") for k, v in s[part].items())
        rows = [[r["run"], *(r["object"][k] for k in OBJECT), *(r["launch"][k] for k in LAUNCH),
                 *(r[k] for k in MEASURED), set_text(r["set"])] for r in self.rows]
        return COLUMNS, rows


def interaction_evidence(rows):
    """Could an analyst who knows the real-world physics have found the new law in these runs?

    Takes each run's flight time relative to what gravity and drag alone predict, regresses
    that on the object's numeric properties (and shape), and tests every pair's product.
    reflectance:temperature counts as identifiable if it passes a Bonferroni threshold over
    the testable pairs. Not shown to the explorer.
    """
    n = len(rows)
    if n < 2:
        return {"n": n, "estimable": False, "identifiable": False}
    expected, _, _ = simulate([r["object"] for r in rows], [r["launch"] for r in rows], kappa=0.0)
    y = np.array([r["flight_time"] for r in rows]) / expected - 1
    P = {p: np.array([float(r["object"][p]) for r in rows]) for p in NUMERIC}
    shape = np.array([r["object"]["shape"] for r in rows])
    Q = _basis(np.column_stack([np.ones(n), *P.values(), shape == "cube", shape == "cylinder"]))
    dof = n - Q.shape[1] - 1
    if dof < 1:
        return {"n": n, "estimable": False, "identifiable": False}
    ry = y - Q @ (Q.T @ y)
    screen = {}
    for a, b in itertools.combinations(NUMERIC, 2):
        prod = P[a] * P[b]
        rp = prod - Q @ (Q.T @ prod)
        ss = float(rp @ rp)
        if ss <= RANK_TOL**2 * float(prod @ prod) or ss == 0:
            continue
        coef = float(rp @ ry) / ss
        se = math.sqrt(max(float(ry @ ry) - coef * coef * ss, 0.0) / dof / ss)
        t = coef / se if se > 0 else math.copysign(math.inf, coef)
        screen[f"{a}:{b}"] = (t, float(2 * stats.t.sf(abs(t), dof)))
    target = "reflectance:temperature"
    if target not in screen:
        return {"n": n, "estimable": False, "identifiable": False, "pairs_testable": len(screen)}
    t, p = screen[target]
    order = sorted(screen, key=lambda k: -abs(screen[k][0]))
    return {
        "n": n,
        "estimable": True,
        "t": round(t, 2),
        "p": float(f"{p:.3g}"),
        "rank": order.index(target) + 1,
        "pairs_testable": len(screen),
        "identifiable": p < 0.05 / len(screen),
    }


def law_tests(seed=2026, pairs=20):
    """Held-out experiments for the submitted law, in pairs that differ only in colour and
    temperature: one where the new law is strong, one where it is absent."""
    rng = np.random.default_rng(seed)
    lab = PhysicsLab(seed)
    cases = []
    for _ in range(pairs):
        obj = lab.random_object()
        launch = {
            "height": round(float(rng.uniform(2, 50)), 1),
            "speed": round(float(rng.uniform(0, 20)), 1),
            "angle": round(float(rng.uniform(-30, 60)), 1),
            "air_density": round(float(rng.choice([0.0, 1.2, rng.uniform(0, 2.4)])), 2),
        }
        hot = rng.random() < 0.5
        strong = obj | {
            "temperature": round(float(rng.uniform(65, 80) if hot else rng.uniform(-20, -10)), 1),
            "reflectance": round(float(rng.uniform(0.0, 0.1) if rng.random() < 0.5 else rng.uniform(0.9, 1.0)), 2),
        }
        neutral = strong | ({"temperature": 20.0} if rng.random() < 0.5 else {"reflectance": 0.5})
        cases += [{"object": strong, "launch": launch, "strong": True}, {"object": neutral, "launch": launch, "strong": False}]
    return cases


def law_truth(cases, kappa=KAPPA):
    t, d, v = simulate([c["object"] for c in cases], [c["launch"] for c in cases], kappa)
    return np.column_stack([t, d, v])


LAW_HARNESS = """
import contextlib, io, json
namespace = {{}}
with contextlib.redirect_stdout(io.StringIO()):
    exec(compile({source!r}, "<law>", "exec"), namespace)
cases = json.loads({cases!r})
out = []
for c in cases:
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            p = namespace["predict"](dict(c["object"]), dict(c["launch"]))
        out.append([float(p["flight_time"]), float(p["distance"]), float(p["impact_speed"])])
    except Exception:
        out.append(None)
print("PREDICTIONS " + json.dumps(out))
"""


def law_program(law_source, cases):
    payload = [{"object": c["object"], "launch": c["launch"]} for c in cases]
    return LAW_HARNESS.format(source=law_source, cases=json.dumps(payload))


def law_predictions(output):
    """The predictions printed by law_program, or None if it did not finish."""
    lines = [line for line in output.splitlines() if line.startswith("PREDICTIONS ")]
    return json.loads(lines[-1][len("PREDICTIONS "):]) if lines else None
