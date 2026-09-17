"""Label-hidden review export, extraction aid, review lock, and unmasking.

Export: each successful paper gets a random ID, the order is shuffled, and only
the paper text is exposed.  The ID -> (phase, dataset, condition, model, rep)
mapping is written to a separate directory.  Paper *content* may still reveal
its condition (e.g. it discusses a supplied table), so this is label-hidden
review, not complete blinding.

Lock: before unmasking, the filled review forms are hashed into LOCK.json.
Unmasking refuses to run unless the lock exists and every form still matches.
"""
from __future__ import annotations

import copy
import csv
import json
import re
import secrets
from pathlib import Path

from .common import read_json, sha256_file, sha256_text, utc_now, utc_stamp, write_json, write_text
from .paths import REVIEW_DIR, REVIEW_SCHEMA_PATH, RUNS_DIR


class ReviewError(RuntimeError):
    pass


def load_schema(path: Path = REVIEW_SCHEMA_PATH) -> dict:
    return read_json(path)


def empty_form(schema: dict, review_id: str) -> dict:
    form = copy.deepcopy(schema["form_template"])
    form["review_id"] = review_id
    return form


def planned_cache_keys(phase: str, runs_dir: Path = RUNS_DIR) -> dict[str, dict]:
    """cache_key -> scheduled call, from runs/<phase>/schedule.json."""
    sched_path = runs_dir / phase / "schedule.json"
    if not sched_path.exists():
        raise ReviewError(f"{sched_path} is missing: export must be driven by the schedule that was executed, "
                          f"not by whatever files happen to sit in records/. Run `cli.py run --phase {phase}` first.")
    return {c["cache_key"]: c for c in read_json(sched_path)["calls"]}


def collect_success_records(phase: str, runs_dir: Path = RUNS_DIR) -> tuple[list[dict], list[dict], list[dict]]:
    """Records split into (scorable, off-plan, refused).

    * scorable  -- status "success", in the current schedule: these become papers.
    * off-plan  -- left over from a superseded prompt or request setting.  The cache
      key is part of the record filename, so a changed prompt writes new files and
      the old ones stay behind; scoring them would double-count cells.
    * refused   -- status "refused": the provider explicitly declined.  A real
      outcome of a scheduled call, reported with failures and truncations, but not
      a paper, so it is never handed to a reviewer as one.

    Off-plan and refused are returned so the caller can surface them; only the
    first list is ever exported.
    """
    rec_dir = runs_dir / phase / "records"
    if not rec_dir.exists():
        return [], [], []
    planned = planned_cache_keys(phase, runs_dir)
    in_plan, off_plan, refused = [], [], []
    seen: dict[str, str] = {}
    for path in sorted(rec_dir.glob("*.json")):
        r = read_json(path)
        status = r.get("status")
        if status not in ("success", "refused"):
            continue
        key = r.get("cache_key")
        if key in seen:
            raise ReviewError(
                f"two records claim the same scheduled call: {seen[key]} and {path.name} both carry "
                f"cache_key {key!r}. One scheduled call must map to exactly one record, or the paper is "
                f"exported twice and that cell is double-counted. Remove or move aside the duplicate.")
        seen[key] = path.name
        if key not in planned:
            off_plan.append({"record_file": path.name, "cache_key": r.get("cache_key"),
                             "prompt_hash": r.get("prompt_hash") or "", "dataset": r.get("dataset"),
                             "condition": r.get("condition"), "rep": r.get("rep"), "status": status})
            continue
        if status == "refused":
            refused.append({"record_file": path.name, "cache_key": r.get("cache_key"),
                            "dataset": r.get("dataset"), "condition": r.get("condition"), "rep": r.get("rep"),
                            "refusal_reason": r.get("refusal_reason"),
                            "finish_reason": r.get("finish_reason")})
        elif isinstance(r.get("content"), str):
            in_plan.append(r)
    return in_plan, off_plan, refused


def export_anonymized(phase: str, *, runs_dir: Path = RUNS_DIR, review_dir: Path = REVIEW_DIR,
                      schema: dict | None = None, rng: secrets.SystemRandom | None = None) -> dict:
    records, off_plan, refused = collect_success_records(phase, runs_dir)
    if not records:
        extra = [f"{len(off_plan)} off-plan" for _ in (1,) if off_plan] + [f"{len(refused)} refused" for _ in (1,) if refused]
        raise ReviewError(f"no scorable records for phase {phase!r} under {runs_dir} that match "
                          f"runs/{phase}/schedule.json"
                          + (f" ({', '.join(extra)} record(s) ignored)" if extra else ""))
    schema = schema or load_schema()
    rng = rng or secrets.SystemRandom()
    stamp = utc_stamp()
    export_dir = review_dir / phase / f"export_{stamp}"
    mapping_dir = review_dir / phase / "mapping"
    (export_dir / "papers").mkdir(parents=True, exist_ok=False)
    (export_dir / "forms").mkdir(parents=True, exist_ok=True)
    mapping_dir.mkdir(parents=True, exist_ok=True)

    ids: set[str] = set()
    order = list(range(len(records)))
    rng.shuffle(order)
    mapping = []
    for k, idx in enumerate(order):
        rec = records[idx]
        while True:
            rid = "P" + secrets.token_hex(3)
            if rid not in ids:
                ids.add(rid)
                break
        write_text(export_dir / "papers" / f"{rid}.md", rec["content"])   # paper text, complete
        write_json(export_dir / "forms" / f"{rid}.json", empty_form(schema, rid))
        mapping.append({"review_id": rid, "export_position": k, "phase": rec["phase"], "dataset": rec["dataset"],
                        "condition": rec["condition"], "model_key": rec["model_key"], "requested_model": rec["requested_model"],
                        "response_model": rec.get("response_model"), "rep": rec["rep"], "cache_key": rec["cache_key"],
                        "truncated": bool(rec.get("truncated")), "prompt_hash": rec["prompt_hash"],
                        "paper_sha256": sha256_text(rec["content"])})
    mapping_path = mapping_dir / f"mapping_{stamp}.json"
    write_json(mapping_path, {"export_dir": str(export_dir), "created_at": utc_now(), "phase": phase, "entries": mapping})
    write_json(export_dir / "EXPORT_INFO.json", {
        "phase": phase, "created_at": utc_now(), "n_papers": len(records),
        "blinding_note": "Label-hidden review: dataset, condition, model and repetition are withheld and the order is shuffled, "
                         "but paper content may reveal its condition (e.g. by discussing supplied tables). Mapping is stored separately.",
        "id_generation": "secrets.token_hex; order shuffled with SystemRandom; reproducible only via the saved mapping file",
        "mapping_location": str(mapping_dir),
        "selection": f"only successful records listed in runs/{phase}/schedule.json (matched on the scheduled "
                     f"call identity); explicit provider refusals are recorded but are not papers",
        "n_off_plan_records_excluded": len(off_plan),
        "n_refused_records_excluded": len(refused),
    })
    write_text(export_dir / "README_REVIEWER.md", _reviewer_readme(len(records)))
    ids = {p.stem for p in (export_dir / "papers").glob("*.md")}
    form_ids = {p.stem for p in (export_dir / "forms").glob("*.json")}
    if ids != form_ids:
        raise ReviewError(f"export is inconsistent: {len(ids)} papers but {len(form_ids)} forms "
                          f"(only in papers: {sorted(ids - form_ids)}; only in forms: {sorted(form_ids - ids)})")
    return {"export_dir": str(export_dir), "mapping_path": str(mapping_path), "n_papers": len(records),
            "off_plan_records": off_plan, "refused_records": refused}


def _reviewer_readme(n: int) -> str:
    return f"""# Reviewer instructions ({n} papers)

1. Read RUBRIC.md in experiments/information_conditions/ first.
2. For each `papers/<ID>.md`, fill `forms/<ID>.json`. Use the enumerations in review_schema.json.
3. Score claim strength by what the sentence asserts, not by the section it sits in. Save the supporting quote and section.
4. If a paper contradicts itself about a target, set contradictory_statements=true and record both quotes.
5. You are not told which dataset or condition a paper came from. Do not try to infer it; score the text.
6. When all forms are filled, run `cli.py lock-reviews --export-dir <this dir>` before anyone unmasks.

Optional aid: `aid/<ID>.json` (if present) lists regex hits for interaction terms and keywords. It is only a pointer to passages; it does not score anything.
"""


# ---------------------------------------------------------------------------
# Extraction aid (regex only; no model calls)
# ---------------------------------------------------------------------------

# Two separate separator classes.  Product notation ("X4*X5", "X4 x X5") asserts a
# term; mere co-mention ("X4 and X5") does not, and lumping them together inflates
# the pointer list.  Both are reported, under different keys.
_PROD_SEP = r"\s*(?:\*|×|x|·|\.|:)\s*"
_WORD_SEP = r"\s*(?:by|and|with|,|\s)\s*"
_TARGET_PAIRS = {"X4*X5": ("4", "5"), "X4*X20": ("4", "20"), "X19*X5": ("19", "5"), "X19*X20": ("19", "20")}


def _pair_pattern(a: str, b: str, sep: str) -> re.Pattern:
    return re.compile(rf"\bX\s*{a}" + sep + rf"X\s*{b}\b|\bX\s*{b}" + sep + rf"X\s*{a}\b", re.I)


_TERM_PATTERNS = {name: _pair_pattern(a, b, _PROD_SEP) for name, (a, b) in _TARGET_PAIRS.items()}
_CO_MENTION_PATTERNS = {name: _pair_pattern(a, b, _WORD_SEP) for name, (a, b) in _TARGET_PAIRS.items()}
_GENERIC_PRODUCT = re.compile(r"\bX(\d{1,2})\s*(?:\*|×|·|:)\s*X(\d{1,2})\b|\bX(\d{1,2})\s*(?:\^2|²|squared)", re.I)
# The review form and RUBRIC.md spell the proxy pair X19*X5; the numeric sort used to
# build generic term names would spell it X5*X19.  Emit the form's spelling so the
# reviewer does not have to translate.
_FORM_TERM_LABEL = {"X5*X19": "X19*X5"}
_KEYWORDS = {
    "interaction": re.compile(r"interact", re.I),
    "heteroscedasticity": re.compile(r"heterosc|heterosk|non-constant variance|variance of (the )?residual", re.I),
    "nonlinear": re.compile(r"non-?linear|quadratic|curvature|polynomial", re.I),
    "misspecification": re.compile(r"misspecif|omitted|missing term|unexplained variance|residual", re.I),
    "multiple_testing": re.compile(r"multiple (comparison|testing)|bonferroni|false discovery|fdr|family-?wise|holm|benjamini", re.I),
    "candidate_count": re.compile(r"\b(210|190|20)\b\s*(terms|tests|candidates|comparisons|hypotheses|correlations)", re.I),
    "p_from_r_n": re.compile(r"t\s*=\s*r\s*\*?\s*sqrt|r\s*\*?\s*sqrt\(\s*n|sqrt\(\(?n\s*-\s*2|t-statistic|t\s*=\s*\d", re.I),
    "proxy_direction": re.compile(r"cannot (determine|establish|distinguish) (the )?direction|which .* (is|are) (the )?(cause|proxy)|direction of (the )?(proxy|relationship)|proxy", re.I),
    "overlapping_information": re.compile(r"redundan|collinear|multicollinear|proxy|overlap", re.I),
    "association_vs_mechanism": re.compile(r"causal|causation|mechanism|generating process|association", re.I),
    "computation_claims": re.compile(r"\b(we (ran|fitted|fit|computed|estimated|performed|conducted)|was fitted|were fitted|regression output|our model yielded)\b", re.I),
}


def _snippets(text: str, pattern: re.Pattern, width: int = 160, limit: int = 12) -> list[str]:
    out = []
    for m in pattern.finditer(text):
        s = max(0, m.start() - width)
        e = min(len(text), m.end() + width)
        out.append(text[s:e].replace("\n", " "))
        if len(out) >= limit:
            break
    return out


def extraction_aid(text: str) -> dict:
    products = set()
    for m in _GENERIC_PRODUCT.finditer(text):
        if m.group(1) and m.group(2):
            a, b = sorted((int(m.group(1)), int(m.group(2))))
            name = f"X{a}^2" if a == b else f"X{a}*X{b}"
            products.add(_FORM_TERM_LABEL.get(name, name))
        elif m.group(3):
            products.add(f"X{int(m.group(3))}^2")
    return {
        "note": "Regex pointer only. Reviewers must read the passages; nothing here is a score. "
                "'target_terms' are product notations (X4*X5, X4 x X5); 'target_term_co_mentions' are the two "
                "variables merely named together ('X4 and X5'), which is not by itself a claim about a product.",
        "target_terms": {name: _snippets(text, pat) for name, pat in _TERM_PATTERNS.items()},
        "target_term_co_mentions": {name: _snippets(text, pat) for name, pat in _CO_MENTION_PATTERNS.items()},
        "second_order_terms_mentioned": sorted(products, key=lambda s: (len(s), s)),
        "keywords": {name: _snippets(text, pat, width=120, limit=8) for name, pat in _KEYWORDS.items()},
        "paper_chars": len(text),
    }


_NUMBER = re.compile(r"(?<![\w.])-?\d+\.\d{2,}(?![\w.])")


def number_support_check(paper_text: str, supplied_text: str) -> dict:
    """Numbers with >=2 decimals in the paper that do not appear in the supplied
    input at 2, 3 or 4 decimals.  Aid for the 'unsupported numerical results'
    field after unmasking; derived quantities (p-values, t statistics) will
    legitimately appear here, so this is a pointer, not a verdict."""
    supplied_numbers = set(_NUMBER.findall(supplied_text))
    supplied_rounded = set()
    for s in supplied_numbers:
        v = float(s)
        for d in (2, 3, 4):
            supplied_rounded.add(f"{v:.{d}f}")
            supplied_rounded.add(f"{abs(v):.{d}f}")
    found, unsupported = [], []
    for s in _NUMBER.findall(paper_text):
        v = float(s)
        keys = {f"{v:.{d}f}" for d in (2, 3, 4)} | {f"{abs(v):.{d}f}" for d in (2, 3, 4)}
        (found if keys & supplied_rounded else unsupported).append(s)
    return {"n_numbers_in_paper": len(found) + len(unsupported), "n_found_in_supplied_input": len(found),
            "not_found_in_supplied_input": sorted(set(unsupported), key=lambda x: float(x))}


# ---------------------------------------------------------------------------
# Lock and unmask
# ---------------------------------------------------------------------------

def _form_paths(export_dir: Path) -> list[Path]:
    return sorted((export_dir / "forms").glob("*.json"))


def _get(d: dict, dotted: str):
    cur = d
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def validate_form(form: dict, schema: dict) -> list[str]:
    problems = []
    for field, enum_name in schema["required_enum_fields"].items():
        val = _get(form, field)
        if val in (None, ""):
            problems.append(f"{field}: empty")
        elif val not in schema["enums"][enum_name]:
            problems.append(f"{field}: {val!r} not in {schema['enums'][enum_name]}")
    for entry in form.get("other_second_order_terms", []):
        if entry.get("strength") not in schema["enums"]["strength"]:
            problems.append(f"other_second_order_terms[{entry.get('term')}]: bad strength {entry.get('strength')!r}")
    return problems


def lock_reviews(export_dir: Path, *, schema: dict | None = None, allow_incomplete: bool = False,
                 relock_note: str | None = None) -> Path:
    """Hash the filled forms.  Refuses to silently replace an existing, different lock.

    Re-locking identical content is a no-op and stays allowed, so the command is safe to
    repeat.  Re-locking *changed* content needs ``relock_note``: without it, an edit made
    after unmasking could be re-locked and would then verify cleanly, which would destroy
    the guarantee the lock exists to provide.
    """
    schema = schema or load_schema()
    forms = _form_paths(export_dir)
    if not forms:
        raise ReviewError("no forms to lock")

    papers = {p.stem for p in (export_dir / "papers").glob("*.md")}
    names = {p.stem for p in forms}
    if papers and papers != names:
        raise ReviewError(
            f"papers and forms do not correspond: {len(papers)} papers, {len(names)} forms "
            f"(paper with no form: {sorted(papers - names)}; form with no paper: {sorted(names - papers)}). "
            f"Locking a partial set would silently drop a paper from every downstream count.")

    incomplete, hashes = {}, {}
    for p in forms:
        problems = validate_form(read_json(p), schema)
        if problems:
            incomplete[p.name] = problems
        hashes[p.name] = sha256_file(p)
    if incomplete and not allow_incomplete:
        detail = "\n".join(f"  {k}: {v[:3]}{' ...' if len(v) > 3 else ''}" for k, v in incomplete.items())
        raise ReviewError("incomplete or invalid forms (use --allow-incomplete to lock anyway, recorded):\n" + detail)

    path = export_dir / "LOCK.json"
    history = []
    if path.exists():
        prev = read_json(path)
        if prev.get("form_sha256") == hashes:
            return path                                   # identical content: no-op
        changed = sorted(n for n in set(prev.get("form_sha256", {})) | set(hashes)
                         if prev.get("form_sha256", {}).get(n) != hashes.get(n))
        if not relock_note:
            raise ReviewError(
                "LOCK.json already exists and the forms have changed since it was written; refusing to "
                f"overwrite it. Changed: {changed[:8]}{' ...' if len(changed) > 8 else ''}. A lock that can be "
                "silently replaced after unmasking guarantees nothing. Record the correction separately, or "
                "pass an explicit relock note if the forms legitimately changed before any unmasking.")
        history = prev.get("superseded_locks", []) + [
            {k: prev.get(k) for k in ("created_at", "n_forms", "form_sha256")} | {"relock_note": relock_note}]

    lock = {"created_at": utc_now(), "n_forms": len(forms), "form_sha256": hashes,
            "incomplete_forms_at_lock": incomplete, "note": "Claim extraction locked before unmasking."}
    if history:
        lock["superseded_locks"] = history
    write_json(path, lock)
    return path


def verify_lock(export_dir: Path) -> tuple[bool, list[str]]:
    lock_path = export_dir / "LOCK.json"
    if not lock_path.exists():
        return False, ["LOCK.json missing: run lock-reviews first"]
    lock = read_json(lock_path)
    problems = []
    current = {p.name: sha256_file(p) for p in _form_paths(export_dir)}
    for name, h in lock["form_sha256"].items():
        if name not in current:
            problems.append(f"{name}: form missing since lock")
        elif current[name] != h:
            problems.append(f"{name}: modified after lock")
    for name in current:
        if name not in lock["form_sha256"]:
            problems.append(f"{name}: form added after lock")
    return not problems, problems


def unmask(export_dir: Path, mapping_path: Path, *, inputs_dir: Path | None = None) -> dict:
    ok, problems = verify_lock(export_dir)
    if not ok:
        raise ReviewError("refusing to unmask: " + "; ".join(problems))
    mapping = {e["review_id"]: e for e in read_json(mapping_path)["entries"]}
    forms = {p.stem for p in _form_paths(export_dir)}
    papers = {p.stem for p in (export_dir / "papers").glob("*.md")}
    if forms != papers:
        raise ReviewError(f"papers and forms do not correspond: only in papers {sorted(papers - forms)}; "
                          f"only in forms {sorted(forms - papers)}")
    if forms != set(mapping):
        raise ReviewError(f"forms and mapping do not correspond: in mapping but not scored "
                          f"{sorted(set(mapping) - forms)}; scored but not in mapping {sorted(forms - set(mapping))}")
    rows = []
    for p in _form_paths(export_dir):
        form = read_json(p)
        rid = p.stem
        if rid not in mapping:
            raise ReviewError(f"{rid}: not in mapping")
        paper = (export_dir / "papers" / f"{rid}.md").read_text()
        meta = mapping[rid]
        if sha256_text(paper) != meta["paper_sha256"]:
            raise ReviewError(f"{rid}: paper text changed since export")
        row = {"review_id": rid, **{k: meta[k] for k in ("phase", "dataset", "condition", "model_key", "requested_model",
                                                            "response_model", "rep", "cache_key", "truncated", "prompt_hash")},
               "form": form}
        if inputs_dir is not None:
            supplied = (inputs_dir / f"{meta['dataset']}__{meta['condition']}.user.txt")
            if supplied.exists():
                row["number_support_check"] = number_support_check(paper, supplied.read_text())
                row["supplied_input_file"] = str(supplied.name)
        rows.append(row)
    out_json = export_dir / "unmasked_reviews.json"
    write_json(out_json, {"created_at": utc_now(), "lock": read_json(export_dir / "LOCK.json"), "rows": rows})
    out_csv = export_dir / "unmasked_summary.csv"
    _write_unmasked_csv(out_csv, rows)
    return {"unmasked_json": str(out_json), "unmasked_csv": str(out_csv), "n_rows": len(rows),
            "csv_columns": _UNMASKED_CSV_COLUMNS}


# Every column REPORT.md summarises per combination, so the report can be filled from
# this file alone: the four target strengths and their contradiction flags, the
# structural explanations, the overlap/proxy-direction judgements and all eight
# auxiliary fields.
_TARGET_FIELDS = {
    "exact_X4_X5": "exact_interaction_X4_X5",
    "X4*X20": "proxy_related_interactions.X4*X20",
    "X19*X5": "proxy_related_interactions.X19*X5",
    "X19*X20": "proxy_related_interactions.X19*X20",
}
_AUX_FIELDS = ["multiplicative_term_expressed_correctly", "association_vs_generating_mechanism_distinguished",
               "p_values_computed_from_r_and_n", "numerical_plausibility_of_reported_calculations",
               "multiple_testing_recognized", "candidate_count_stated", "multiplicity_handling_reasonable",
               "unsupported_numerical_results_or_claims_of_computation"]
_UNMASKED_CSV_COLUMNS = (
    ["review_id", "phase", "dataset", "condition", "rep", "truncated"]
    + [c for k in _TARGET_FIELDS for c in (k, f"{k}__contradictory")]
    + ["any_contradictory_statements", "heteroscedasticity", "other_nonlinear", "misspecification",
       "n_other_second_order_terms", "other_second_order_terms_supported",
       "any_term_claimed_supported", "overlap_recognized", "proxy_direction_caveat"]
    + [f"aux__{name}" for name in _AUX_FIELDS]
)


def _write_unmasked_csv(out_csv: Path, rows: list[dict]) -> None:
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(_UNMASKED_CSV_COLUMNS)
        for r in rows:
            fm = r["form"]
            others = fm.get("other_second_order_terms") or []
            contradictions = [bool(_get(fm, f"{base}.contradictory_statements")) for base in _TARGET_FIELDS.values()]
            cells = [r["review_id"], r["phase"], r["dataset"], r["condition"], r["rep"], r["truncated"]]
            for base in _TARGET_FIELDS.values():
                cells += [_get(fm, f"{base}.strength"), bool(_get(fm, f"{base}.contradictory_statements"))]
            cells += [
                any(contradictions),
                _get(fm, "structural_non_interaction_explanations.heteroscedasticity.strength"),
                _get(fm, "structural_non_interaction_explanations.other_nonlinear_structure.strength"),
                _get(fm, "structural_non_interaction_explanations.model_misspecification.strength"),
                len(others),
                ";".join(str(e.get("term")) for e in others if e.get("strength") == "supported"),
                _get(fm, "any_feature_or_term_claimed_supported"),
                _get(fm, "overlapping_information_among_correlated_predictors_recognized.value"),
                _get(fm, "proxy_direction_caveat_acknowledged.value"),
            ]
            cells += [_get(fm, f"auxiliary.{name}.value") for name in _AUX_FIELDS]
            w.writerow(cells)
