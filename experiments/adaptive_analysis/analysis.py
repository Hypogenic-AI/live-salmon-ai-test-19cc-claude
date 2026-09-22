"""Shared, deterministic analysis tools. This module receives discovery data only.

No tool knows the data condition, variable roles, or held-out targets. A session
owns its fitted models and cache; fixed and adaptive workflows get separate
sessions. Scans count every candidate's CV fits, including undisplayed rows.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from itertools import combinations
import json
from time import perf_counter

import numpy as np
import pandas as pd
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import KFold

from src.baseline_analysis import fit_ols


class AnalysisSession:
    def __init__(self, discovery: pd.DataFrame, seed: int = 0, folds: int = 5,
                 top_k: int = 10):
        if (not isinstance(discovery, pd.DataFrame) or "Y" not in discovery
                or not discovery.columns.is_unique):
            raise ValueError("Discovery must be a dataframe with unique columns and Y")
        self.features = [c for c in discovery.columns if c != "Y"]
        if len(self.features) < 3 or any(not isinstance(c, str) for c in self.features):
            raise ValueError("At least three named features are required")
        if not np.isfinite(discovery.to_numpy(dtype=float)).all():
            raise ValueError("Discovery data must be finite and numeric")
        if not isinstance(folds, int) or not 2 <= folds <= len(discovery):
            raise ValueError("Invalid number of CV folds")
        if not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k must be positive")
        self._X = discovery[self.features].copy(deep=True)
        self._y = discovery["Y"].to_numpy(dtype=float, copy=True)
        self.folds = list(KFold(n_splits=folds, shuffle=True,
                               random_state=seed).split(self._X))
        self.top_k = top_k
        self.records: dict[str, dict] = {}
        self._estimators: dict[str, object] = {}
        self.exposed_model_ids: set[str] = set()
        self.evidence_ids: set[str] = set()
        self.stats = dict(candidate_models=0, cv_fits=0, final_fits=0,
                          cache_hits=0, analysis_seconds=0.0)

    def _spec(self, spec: dict) -> dict:
        if not isinstance(spec, dict):
            raise ValueError("Model spec must be an object")
        kind = spec.get("kind")
        allowed = {"null": {"kind"}, "linear": {"kind"},
                   "interaction": {"kind", "pair"},
                   "conditional": {"kind", "pair", "gate"}}
        if not isinstance(kind, str) or kind not in allowed or set(spec) != allowed[kind]:
            raise ValueError("Unknown model kind or unexpected model arguments")
        out = {"kind": kind}
        if kind in {"interaction", "conditional"}:
            pair = spec["pair"]
            if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                    or any(not isinstance(f, str) or f not in self.features for f in pair)
                    or pair[0] == pair[1]):
                raise ValueError("pair must contain two distinct observed features")
            out["pair"] = sorted(pair)
        if kind == "conditional":
            gate = spec["gate"]
            if not isinstance(gate, str) or gate not in self.features or gate in out["pair"]:
                raise ValueError("gate must be an observed feature outside the pair")
            out["gate"] = gate
        return out

    def _design(self, X: pd.DataFrame, spec: dict) -> pd.DataFrame:
        if spec["kind"] == "null":
            # OLS with a constant column is the intercept-only mean predictor.
            return pd.DataFrame({"constant": np.ones(len(X))}, index=X.index)
        design = X.loc[:, self.features].copy()
        if "pair" in spec:
            a, b = spec["pair"]
            name = f"{a}*{b}"
            design[name] = X[a] * X[b]
            if spec["kind"] == "conditional":
                gate = spec["gate"]
                design[f"{name}|{gate}>0"] = design[name] * (X[gate] > 0)
        return design

    def _public(self, record: dict) -> dict:
        row = deepcopy(record)
        # Baseline main effects are shown once. Candidate tables keep the same
        # effect fields in both workflows, rather than repeating 20 coefficients.
        if row["spec"]["kind"] in {"interaction", "conditional"}:
            row["coefficients"] = {k: v for k, v in row["coefficients"].items()
                                   if k not in self.features}
        self.exposed_model_ids.add(row["model_id"])
        self.evidence_ids.add(row["evidence_id"])
        return row

    def fit_model(self, spec: dict, *, expose: bool = True) -> dict:
        spec = self._spec(spec)
        model_id = "m_" + sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]
        if model_id in self.records:
            self.stats["cache_hits"] += 1
            result = self.records[model_id]
            return self._public(result) if expose else deepcopy(result)
        started = perf_counter()
        design = self._design(self._X, spec)
        fold_mse = []
        for train, valid in self.folds:
            fitted = fit_ols(design.iloc[train], self._y[train])
            self.stats["cv_fits"] += 1
            fold_mse.append(float(mean_squared_error(
                self._y[valid], fitted.predict(design.iloc[valid]))))
        fitted = fit_ols(design, self._y)
        self.stats["final_fits"] += 1
        coefficients = {str(c): float(v) for c, v in zip(design.columns, fitted.coef_)}
        coefficients["intercept"] = float(fitted.intercept_)
        if spec["kind"] == "null":
            coefficients = {"intercept": float(fitted.intercept_)}
        record = dict(model_id=model_id, evidence_id=f"fit:{model_id}", spec=spec,
                      cv_mse=float(np.mean(fold_mse)),
                      cv_mse_se=float(np.std(fold_mse, ddof=1) / np.sqrt(len(fold_mse))),
                      fold_mse=fold_mse,
                      training_mse=float(mean_squared_error(self._y, fitted.predict(design))),
                      coefficients=coefficients)
        if spec["kind"] == "conditional":
            name = "*".join(spec["pair"])
            gate = spec["gate"]
            lo = coefficients[name]
            hi = lo + coefficients[f"{name}|{gate}>0"]
            record["group_slopes"] = {"nonpositive": lo, "positive": hi}
            positive = int((self._X[gate] > 0).sum())
            record["group_sizes"] = {"nonpositive": len(self._X) - positive,
                                     "positive": positive}
        self.records[model_id] = record
        self._estimators[model_id] = fitted
        self.stats["candidate_models"] += 1
        self.stats["analysis_seconds"] += perf_counter() - started
        return self._public(record) if expose else deepcopy(record)

    def _ranked(self, rows: list[dict]) -> list[dict]:
        return sorted(rows, key=lambda r: (r["cv_mse"], r["model_id"]))[:self.top_k]

    def diagnose(self, model_id: str, mode: str, term=None) -> dict:
        if model_id not in self.exposed_model_ids:
            raise ValueError("Diagnosis requires an exposed, fitted model")
        if mode == "pairwise":
            if term is not None:
                raise ValueError("pairwise diagnosis takes no term")
            rows = [self.fit_model({"kind": "interaction", "pair": list(pair)}, expose=False)
                    for pair in combinations(self.features, 2)]
            eid = f"scan:pairwise:{model_id}"
        elif mode == "stability":
            pair = self._spec({"kind": "interaction", "pair": term})["pair"]
            rows = [self.fit_model({"kind": "conditional", "pair": pair, "gate": gate},
                                   expose=False)
                    for gate in self.features if gate not in pair]
            eid = f"scan:stability:{model_id}:{':'.join(pair)}"
        else:
            raise ValueError("Unknown diagnosis mode")
        self.evidence_ids.add(eid)
        return dict(evidence_id=eid, mode=mode, model_id=model_id,
                    interpretation="Candidate CV scores are exploratory, not corrected significance tests.",
                    evaluated_candidates=len(rows),
                    baseline_cv_mse=self.records[model_id]["cv_mse"],
                    candidates=[self._public(r) for r in self._ranked(rows)])

    def fixed_evidence(self) -> dict:
        """Exhaustive precomputed evidence, with no true-variable shortcuts."""
        baselines = [self.fit_model({"kind": k}) for k in ("null", "linear")]
        pairs = list(combinations(self.features, 2))
        global_rows = [self.fit_model({"kind": "interaction", "pair": list(p)}, expose=False)
                       for p in pairs]
        conditional_rows = [self.fit_model({"kind": "conditional", "pair": list(p), "gate": g},
                                           expose=False)
                            for p in pairs for g in self.features if g not in p]
        self.evidence_ids.add("fixed:summary")
        return dict(evidence_id="fixed:summary", baselines=baselines,
                    interpretation="Candidate CV scores are exploratory, not corrected significance tests.",
                    global_candidates=[self._public(r) for r in self._ranked(global_rows)],
                    conditional_candidates=[self._public(r) for r in self._ranked(conditional_rows)],
                    candidate_counts=dict(null=1, linear=1, interaction=len(global_rows),
                                          conditional=len(conditional_rows)))

    def predict(self, model_id: str, X: pd.DataFrame) -> np.ndarray:
        """Called only by the evaluator after submission; no fitting or updates."""
        if model_id not in self.records:
            raise ValueError("Unknown fitted model")
        if not isinstance(X, pd.DataFrame) or not set(self.features).issubset(X.columns):
            raise ValueError("Prediction data must contain all observed features")
        if "Y" in X.columns or not np.isfinite(X[self.features].to_numpy(dtype=float)).all():
            raise ValueError("Prediction input must be finite features without targets")
        return self._estimators[model_id].predict(self._design(X, self.records[model_id]["spec"]))
