"""
A system with 20 adjustable features (X1..X20) and one outcome Y, built on the same
formula as the original Live Salmon study, but run as a laboratory: the explorer
decides what to set in each run and collects its own data.

Hidden structure (a structural causal model). The natural values below apply only to
features the explorer does not set in a given run:

    X1..X15 ~ N(0, 1)
    X16 = 0.7 X1 + 0.3 e      X17 = 0.6 X2 + 0.4 e      X18 = 0.5 X3 + 0.5 e
    X19 = 0.8 X4 + 0.2 e      X20 = 0.65 X5 + 0.35 e    (e ~ N(0, 1), fresh each time)
    Y   = 2 X1 + 0.5 X2 - 1.5 X3 + 0.8 X4 X5 + N(0, 1)

These are the generator and coefficients of datasets/generate_live_salmon_data.py.
Running with nothing set therefore draws fresh rows of the original study's data. Setting
a feature overrides its natural value, so setting any of X16..X20 cuts its link to
X1..X5 and it has no effect on Y. The X4 X5 interaction cannot be seen in an experiment
that changes one of the two while the other is held at zero.
"""

import itertools
import re

import numpy as np
from scipy import stats

NAMES = [f"X{i}" for i in range(1, 21)]
SET_RANGE = (-3.0, 3.0)
PROXIES = {"X16": ("X1", 0.7, 0.3), "X17": ("X2", 0.6, 0.4), "X18": ("X3", 0.5, 0.5),
           "X19": ("X4", 0.8, 0.2), "X20": ("X5", 0.65, 0.35)}
NOISE_SD = 1.0
DECIMALS = 2
MAX_FIT_TERMS = 40
ANALYSES = ("fit", "correlations", "summary")
RANK_TOL = 1e-9  # singular values below this fraction of the largest count as zero
_TERM = re.compile(r"^X(\d{1,2})(?::X(\d{1,2})|\^2)?$")


def true_mean(x):
    """Expected Y for a full setting of the features (dict name -> value)."""
    return 2 * x["X1"] + 0.5 * x["X2"] - 1.5 * x["X3"] + 0.8 * x["X4"] * x["X5"]


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and bool(np.isfinite(v))


def _num(v, digits):
    return None if not np.isfinite(v) else round(float(v), digits)


def _basis(M):
    """Orthonormal basis for the column space of M."""
    U, s, _ = np.linalg.svd(M, full_matrices=False)
    if s.size == 0 or s[0] == 0:
        return U[:, :0]
    return U[:, s > s[0] * RANK_TOL]


def _parse_term(term):
    m = _TERM.match(term)
    if not m:
        raise ValueError(f"cannot read term {term!r}; use X3, X1:X2 or X3^2")
    i = int(m.group(1))
    j = int(m.group(2)) if m.group(2) else (i if term.endswith("^2") else None)
    for k in (i, j):
        if k is not None and not 1 <= k <= 20:
            raise ValueError(f"no feature X{k}")
    return i - 1, (None if j is None else j - 1)


def fit_ols(X, y, formula):
    """Least squares with an intercept. X: (n, 20) array; formula like 'Y ~ X1 + X1:X2'.

    As in R's lm, a term that in these runs is an exact linear combination of the terms
    before it (for example a feature held at one value throughout) is not estimated, and
    the output says so.
    """
    if not isinstance(formula, str) or "~" not in formula or formula.split("~")[0].strip() != "Y":
        raise ValueError("formula must look like 'Y ~ X1 + X2 + X1:X2'")
    terms = [t.strip() for t in formula.split("~", 1)[1].split("+") if t.strip()]
    if not terms:
        raise ValueError("no terms on the right-hand side")
    if len(terms) > MAX_FIT_TERMS:
        raise ValueError(f"at most {MAX_FIT_TERMS} terms")
    cols = [np.ones(len(y))]
    for t in terms:
        i, j = _parse_term(t)
        cols.append(X[:, i] if j is None else X[:, i] * X[:, j])
    D = np.column_stack(cols)
    keep = []
    for k in range(D.shape[1]):
        if _basis(D[:, keep + [k]]).shape[1] == len(keep) + 1:
            keep.append(k)
    n, p = len(y), len(keep)
    if n <= p:
        raise ValueError(f"need more runs than coefficients ({n} runs, {p} coefficients)")
    Dk = D[:, keep]
    beta, *_ = np.linalg.lstsq(Dk, y, rcond=None)
    resid = y - Dk @ beta
    rss = float(resid @ resid)
    sigma2 = rss / (n - p)
    se = np.sqrt(sigma2 * np.diag(np.linalg.inv(Dk.T @ Dk)))
    with np.errstate(divide="ignore", invalid="ignore"):
        tvals = beta / se
    pvals = 2 * stats.t.sf(np.abs(tvals), n - p)
    estimated = dict(zip(keep, zip(beta, se, tvals, pvals)))
    coefficients = []
    for k, name in enumerate(["Intercept"] + terms):
        if k in estimated:
            b, s, tv, pv = estimated[k]
            coefficients.append({"term": name, "estimate": _num(b, 4), "se": _num(s, 4),
                                 "t": _num(tv, 2), "p": float(f"{pv:.3g}")})
        else:
            coefficients.append({"term": name, "estimate": None,
                                 "note": "not estimable: in these runs it is a linear combination of the terms before it"})
    tss = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - rss / tss if tss > 0 else float("nan")
    return {
        "formula": "Y ~ " + " + ".join(terms),
        "n": n,
        "r2": _num(r2, 4),
        "adj_r2": _num(1 - (1 - r2) * (n - 1) / (n - p), 4),
        "residual_sd": _num(np.sqrt(sigma2), 4),
        "coefficients": coefficients,
    }


def interaction_evidence(X, y):
    """Could a careful analyst have found the X4 X5 interaction in these data?

    Screens every pair of features: fits all 20 main effects plus that pair's product, and
    tests the product. A pair whose product is a linear combination of the main effects
    in these data (for instance because one of the two was always set to the same value)
    cannot be tested. X4:X5 counts as identifiable if it passes a Bonferroni threshold over
    the testable pairs. Not shown to the explorer.
    """
    n = len(y)
    Q = _basis(np.column_stack([np.ones(n), X])) if n else np.zeros((0, 0))
    dof = n - Q.shape[1] - 1
    if dof < 1:
        return {"n": n, "x4x5_estimable": False, "identifiable": False, "note": "too few runs"}
    ry = y - Q @ (Q.T @ y)
    screen = {}
    for i, j in itertools.combinations(range(20), 2):
        prod = X[:, i] * X[:, j]
        rp = prod - Q @ (Q.T @ prod)
        ss = float(rp @ rp)
        if ss <= RANK_TOL**2 * float(prod @ prod) or ss == 0:
            continue
        b = float(rp @ ry) / ss
        se = np.sqrt(max(float(ry @ ry) - b * b * ss, 0.0) / dof / ss)
        t = b / se if se > 0 else np.copysign(np.inf, b)
        screen[f"X{i + 1}:X{j + 1}"] = (b, t, float(2 * stats.t.sf(abs(t), dof)))
    target = "X4:X5"
    if target not in screen:
        return {"n": n, "pair": target, "x4x5_estimable": False, "identifiable": False, "pairs_testable": len(screen)}
    order = sorted(screen, key=lambda k: -abs(screen[k][1]))
    b, t, pv = screen[target]
    threshold = 0.05 / len(screen)
    return {
        "n": n,
        "pair": target,
        "x4x5_estimable": True,
        "x4x5_estimate": round(b, 3),
        "x4x5_t": _num(t, 2),
        "x4x5_p": float(f"{pv:.3g}"),
        "x4x5_rank": order.index(target) + 1,
        "pairs_testable": len(screen),
        "bonferroni_threshold": float(f"{threshold:.3g}"),
        "identifiable": pv < threshold,
    }


class LabWorld:
    def __init__(self, seed, run_budget=300, max_runs_per_turn=100):
        self.rng = np.random.default_rng(seed)
        self.run_budget = run_budget
        self.max_runs_per_turn = max_runs_per_turn
        self.rows = []  # every run: the settings chosen, all 20 values, and Y
        self.analysis_log = []  # every analysis requested, with its result

    def runs_left(self):
        return self.run_budget - len(self.rows)

    def _one_run(self, fixed):
        x = {}
        for i in range(1, 16):
            name = f"X{i}"
            x[name] = fixed[name] if name in fixed else round(float(self.rng.normal()), DECIMALS) + 0.0
        for name, (parent, a, b) in PROXIES.items():
            x[name] = fixed[name] if name in fixed else round(a * x[parent] + b * float(self.rng.normal()), DECIMALS) + 0.0
        y = round(true_mean(x) + float(self.rng.normal(0, NOISE_SD)), DECIMALS) + 0.0  # + 0.0 turns -0.0 into 0.0
        return x, y

    def run_experiments(self, specs):
        """Carry out a turn's experiments. Returns (new rows, messages about anything refused)."""
        new, messages, this_turn = [], [], 0
        if not isinstance(specs, list):
            return new, ["Experiments must be a JSON array."]
        for k, spec in enumerate(specs, 1):
            if not isinstance(spec, dict) or set(spec) - {"set", "n"}:
                messages.append(f"Experiment {k} skipped: use {{\"set\": {{...}}, \"n\": ...}}.")
                continue
            fixed = spec.get("set") or {}
            n = spec.get("n", 1)
            if not isinstance(fixed, dict):
                messages.append(f"Experiment {k} skipped: \"set\" must map feature names to values.")
                continue
            bad = [v for v in fixed if v not in NAMES]
            if bad:
                messages.append(f"Experiment {k} skipped: unknown feature(s) {bad}.")
                continue
            if any(not _is_number(v) or not SET_RANGE[0] <= v <= SET_RANGE[1] for v in fixed.values()):
                messages.append(f"Experiment {k} skipped: set values must be numbers between -3 and 3.")
                continue
            if not isinstance(n, int) or isinstance(n, bool) or n < 1:
                messages.append(f"Experiment {k} skipped: \"n\" must be a positive whole number.")
                continue
            allowed = min(n, self.max_runs_per_turn - this_turn, self.runs_left())
            if allowed < n:
                messages.append(f"Experiment {k}: only {allowed} of {n} runs carried out (per-turn or total limit).")
            fixed = {v: round(float(val), DECIMALS) + 0.0 for v, val in fixed.items()}
            for _ in range(allowed):
                x, y = self._one_run(fixed)
                row = {"run": len(self.rows) + 1, "set": dict(fixed), "X": [x[v] for v in NAMES], "Y": y}
                self.rows.append(row)
                new.append(row)
            this_turn += allowed
            if allowed == 0:
                break
        return new, messages

    def analyse(self, requests):
        """Carry out a turn's analyses. Errors are reported back, never raised."""
        if not isinstance(requests, list):
            return [{"error": "Analyses must be a JSON array."}]
        results = []
        for req in requests:
            try:
                out = self._analyse_one(req)
            except (ValueError, TypeError, np.linalg.LinAlgError) as err:
                out = {"error": str(err)}
            self.analysis_log.append({"request": req, "result": out, "n_rows": len(self.rows)})
            results.append(out)
        return results

    def _analyse_one(self, req):
        kinds = [k for k in req if k in ANALYSES] if isinstance(req, dict) else []
        if len(kinds) != 1 or set(req) - {kinds[0], "runs"}:
            raise ValueError('an analysis has one of "fit", "correlations" or "summary", and optionally "runs"')
        if not self.rows:
            raise ValueError("no data collected yet")
        first, last = self._run_range(req.get("runs"))
        X, y = self.matrix()
        X, y = X[first - 1:last], y[first - 1:last]
        kind, arg = kinds[0], req[kinds[0]]
        if kind == "fit":
            out = fit_ols(X, y, arg)
        else:
            if not isinstance(arg, list) or not arg or len(arg) > 21 or any(v not in NAMES + ["Y"] for v in arg):
                raise ValueError("give a list of up to 21 names from X1..X20 and Y")
            cols = np.column_stack([y if v == "Y" else X[:, NAMES.index(v)] for v in arg])
            if kind == "correlations":
                with np.errstate(invalid="ignore", divide="ignore"):
                    C = np.atleast_2d(np.corrcoef(cols, rowvar=False))
                out = {"correlations": {a: {b: _num(C[i, j], 3) for j, b in enumerate(arg)}
                                        for i, a in enumerate(arg)}}
            else:
                with np.errstate(invalid="ignore", divide="ignore"):
                    sd = cols.std(axis=0, ddof=1) if len(y) > 1 else np.full(len(arg), np.nan)
                out = {"summary": {v: {"mean": _num(cols[:, i].mean(), 3), "sd": _num(sd[i], 3),
                                       "min": _num(cols[:, i].min(), 2), "max": _num(cols[:, i].max(), 2)}
                                   for i, v in enumerate(arg)}}
            out["n"] = len(y)
        out["runs"] = [first, last]
        return out

    def _run_range(self, runs):
        n = len(self.rows)
        if runs is None:
            return 1, n
        ok = (isinstance(runs, list) and len(runs) == 2
              and all(isinstance(r, int) and not isinstance(r, bool) for r in runs)
              and 1 <= runs[0] <= runs[1] <= n)
        if not ok:
            raise ValueError(f'"runs" must be [first, last] with 1 <= first <= last <= {n}')
        return runs[0], runs[1]

    def matrix(self, upto=None):
        rows = self.rows[:upto]
        if not rows:
            return np.zeros((0, 20)), np.zeros(0)
        return np.array([r["X"] for r in rows]), np.array([r["Y"] for r in rows])

    def code_table(self):
        """Columns and rows of the CSV that model-written code sees as `df`."""
        rows = [[r["run"], *r["X"], r["Y"], "; ".join(f"{k}={v:g}" for k, v in r["set"].items())] for r in self.rows]
        return ["run", *NAMES, "Y", "set"], rows

    def evidence(self, upto=None):
        return interaction_evidence(*self.matrix(upto))


QUESTIONS = [
    ({}, "control"),
    ({"X1": 1}, "main"),
    ({"X3": 2}, "main"),
    ({"X2": 2, "X3": -1}, "main"),
    ({"X4": 3}, "main"),
    ({"X4": 2, "X5": 2}, "interaction"),
    ({"X4": 2, "X5": -2}, "interaction"),
    ({"X4": -3, "X5": -3}, "interaction"),
    ({"X1": 1, "X4": 1, "X5": 3}, "interaction"),
    ({"X16": 2}, "proxy"),
    ({"X18": -2}, "proxy"),
]


def questions():
    """Prediction questions. Every feature not listed is set to 0.

    'trap' is the answer of someone who fell for the trap the question probes:
    no interaction for interaction questions; the marginal (correlation-based) slope for
    proxy questions. For other questions there is no trap and 'trap' equals 'true'.
    """
    var = {"X16": 0.7**2 + 0.3**2, "X18": 0.5**2 + 0.5**2}
    cov_with_y = {"X16": 0.7 * 2, "X18": 0.5 * -1.5}
    out = []
    for setting, kind in QUESTIONS:
        setting = dict(setting)
        x = {v: 0.0 for v in NAMES} | {k: float(val) for k, val in setting.items()}
        true = true_mean(x)
        if kind == "interaction":
            trap = true - 0.8 * x["X4"] * x["X5"]
        elif kind == "proxy":
            (name, val), = setting.items()
            trap = cov_with_y[name] / var[name] * val
        else:
            trap = true
        text = ", ".join(f"{k} = {v:g}" for k, v in setting.items()) or "all features at 0"
        out.append({"setting": setting, "kind": kind, "text": text, "true": round(true, 4), "trap": round(trap, 4)})
    return out
