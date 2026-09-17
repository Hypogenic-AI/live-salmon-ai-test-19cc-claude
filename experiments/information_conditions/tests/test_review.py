import json

import pytest

from infocond import review
from infocond.common import write_json
from infocond.paths import INPUTS_DIR


def _record(phase, dataset, condition, rep, content):
    return {"phase": phase, "dataset": dataset, "condition": condition, "rep": rep, "model_key": "gpt-4.1",
            "requested_model": "openai/gpt-4.1", "response_model": "openai/gpt-4.1", "cache_key": f"{dataset}{condition}{rep}",
            "prompt_hash": "ph", "status": "success", "content": content, "truncated": False}


@pytest.fixture
def runs(tmp_path):
    rec_dir = tmp_path / "runs" / "smoke" / "records"
    rec_dir.mkdir(parents=True)
    calls, i = [], 0
    for ds in ("live_salmon", "dead_salmon"):
        for c in ("A", "A_prime", "B"):
            key = f"{ds}{c}1"
            name = f"smoke__{ds}__{c}__gpt-4.1__rep01__{i:016x}.json"
            write_json(rec_dir / name,
                       _record("smoke", ds, c, 1, f"# Paper {i}\n\nMarker-{i}. Y = a + b*X1."))
            calls.append({"dataset": ds, "condition": c, "rep": 1, "prompt_hash": "ph",
                          "cache_key": key, "record_file": name, "schedule_index": i})
            i += 1
    write_json(rec_dir / "smoke__fail.json", {"phase": "smoke", "status": "failed", "content": None, "dataset": "live_salmon", "condition": "A"})
    write_json(tmp_path / "runs" / "smoke" / "schedule.json",
               {"phase": "smoke", "model_key": "gpt-4.1", "model_id": "openai/gpt-4.1",
                "planned_calls": len(calls), "calls": calls})
    return tmp_path / "runs"


def test_export_requires_a_schedule(tmp_path):
    rec_dir = tmp_path / "runs" / "smoke" / "records"
    rec_dir.mkdir(parents=True)
    write_json(rec_dir / "a.json", _record("smoke", "live_salmon", "A", 1, "# Paper"))
    with pytest.raises(review.ReviewError) as exc:
        review.export_anonymized("smoke", runs_dir=tmp_path / "runs", review_dir=tmp_path / "review")
    assert "schedule.json is missing" in str(exc.value)


def test_off_plan_records_are_excluded_and_reported(runs, tmp_path):
    """A prompt change mid-phase leaves the old record behind under its own cache
    key.  It must not be handed to the reviewer as an extra paper."""
    stale = runs / "smoke" / "records" / "smoke__live_salmon__B__gpt-4.1__rep01__STALEKEY00000000.json"
    write_json(stale, _record("smoke", "live_salmon", "B", 1, "# Paper from a superseded prompt"))
    stale_rec = json.loads(stale.read_text())
    stale_rec["cache_key"] = "not-in-the-schedule"
    write_json(stale, stale_rec)

    res = review.export_anonymized("smoke", runs_dir=runs, review_dir=tmp_path / "review")
    assert res["n_papers"] == 6, "the off-plan record must not be exported"
    assert [r["record_file"] for r in res["off_plan_records"]] == [stale.name]
    export_dir = tmp_path / "review" / "smoke" / res["export_dir"].rsplit("/", 1)[1]
    texts = [p.read_text() for p in (export_dir / "papers").glob("*.md")]
    assert not any("superseded" in t for t in texts)
    info = json.loads((export_dir / "EXPORT_INFO.json").read_text())
    assert info["n_off_plan_records_excluded"] == 1


def test_export_hides_labels_and_roundtrips(runs, tmp_path):
    res = review.export_anonymized("smoke", runs_dir=runs, review_dir=tmp_path / "review")
    export_dir = tmp_path / "review" / "smoke" / (res["export_dir"].rsplit("/", 1)[1])
    assert res["n_papers"] == 6
    papers = sorted((export_dir / "papers").glob("*.md"))
    forms = sorted((export_dir / "forms").glob("*.json"))
    assert len(papers) == 6 and len(forms) == 6
    ids = {p.stem for p in papers}
    assert ids == {f.stem for f in forms} and all(i.startswith("P") and len(i) == 7 for i in ids)
    # nothing in the export directory names dataset/condition/model/rep
    for p in list(export_dir.rglob("*")):
        if p.is_file():
            txt = p.read_text()
            for bad in ("live_salmon", "dead_salmon", "A_prime", "gpt-4.1", "rep01", "cache_key"):
                assert bad not in txt, (p, bad)
    # mapping is outside the export dir and reproduces identities
    mapping_path = tmp_path / "review" / "smoke" / "mapping" / res["mapping_path"].rsplit("/", 1)[1]
    assert mapping_path.exists() and export_dir not in mapping_path.parents
    mapping = json.loads(mapping_path.read_text())["entries"]
    assert len(mapping) == 6 and {(m["dataset"], m["condition"]) for m in mapping} == {(d, c) for d in ("live_salmon", "dead_salmon") for c in ("A", "A_prime", "B")}
    markers = {(d, c): i for i, (d, c) in enumerate((d, c) for d in ("live_salmon", "dead_salmon") for c in ("A", "A_prime", "B"))}
    for m in mapping:
        text = (export_dir / "papers" / f"{m['review_id']}.md").read_text()
        assert f"Marker-{markers[(m['dataset'], m['condition'])]}." in text     # paper text preserved verbatim
    info = json.loads((export_dir / "EXPORT_INFO.json").read_text())
    assert "Label-hidden" in info["blinding_note"]
    assert (export_dir / "README_REVIEWER.md").exists()


def _fill(form, strength="absent"):
    schema = review.load_schema()
    for field, enum in schema["required_enum_fields"].items():
        cur = form
        parts = field.split(".")
        for part in parts[:-1]:
            cur = cur[part]
        cur[parts[-1]] = strength if enum == "strength" else schema["enums"][enum][0]
    return form


def test_lock_then_unmask(runs, tmp_path):
    res = review.export_anonymized("smoke", runs_dir=runs, review_dir=tmp_path / "review")
    export_dir = tmp_path / "review" / "smoke" / (res["export_dir"].rsplit("/", 1)[1])
    mapping_path = tmp_path / "review" / "smoke" / "mapping" / res["mapping_path"].rsplit("/", 1)[1]
    # unmask refuses without lock
    with pytest.raises(review.ReviewError):
        review.unmask(export_dir, mapping_path)
    # lock refuses incomplete forms
    with pytest.raises(review.ReviewError):
        review.lock_reviews(export_dir)
    forms = sorted((export_dir / "forms").glob("*.json"))
    for k, f in enumerate(forms):
        form = _fill(json.loads(f.read_text()), strength="proposed" if k == 0 else "absent")
        form["exact_interaction_X4_X5"]["quote"] = "may warrant testing"
        write_json(f, form)
    # invalid enum rejected
    bad = json.loads(forms[1].read_text()); bad["exact_interaction_X4_X5"]["strength"] = "maybe"; write_json(forms[1], bad)
    with pytest.raises(review.ReviewError):
        review.lock_reviews(export_dir)
    bad["exact_interaction_X4_X5"]["strength"] = "absent"; write_json(forms[1], bad)
    lock = review.lock_reviews(export_dir)
    assert lock.exists()
    ok, problems = review.verify_lock(export_dir)
    assert ok and problems == []
    out = review.unmask(export_dir, mapping_path, inputs_dir=INPUTS_DIR)
    rows = json.loads((export_dir / "unmasked_reviews.json").read_text())["rows"]
    assert out["n_rows"] == 6 and {r["dataset"] for r in rows} == {"live_salmon", "dead_salmon"}
    proposed = [r for r in rows if r["form"]["exact_interaction_X4_X5"]["strength"] == "proposed"]
    assert len(proposed) == 1 and proposed[0]["review_id"] == forms[0].stem
    # editing a form after lock blocks unmasking
    f0 = json.loads(forms[0].read_text()); f0["overall_notes"] = "changed"; write_json(forms[0], f0)
    with pytest.raises(review.ReviewError):
        review.unmask(export_dir, mapping_path)


def test_refused_records_are_reported_but_never_exported_as_papers(runs, tmp_path):
    """A refusal is a real outcome of a scheduled call, but it is not a paper."""
    sched_path = runs / "smoke" / "schedule.json"
    sched = json.loads(sched_path.read_text())
    target = sched["calls"][0]
    rec_dir = runs / "smoke" / "records"
    victim = rec_dir / target["record_file"]
    rec = json.loads(victim.read_text())
    rec.update(status="refused", content=None, refusal="I can't help with that request.",
               refusal_reason="message.refusal", finish_reason="stop")
    write_json(victim, rec)

    res = review.export_anonymized("smoke", runs_dir=runs, review_dir=tmp_path / "review")
    assert res["n_papers"] == 5, "the refused call must not become a sixth paper"
    assert [r["record_file"] for r in res["refused_records"]] == [target["record_file"]]
    assert res["refused_records"][0]["refusal_reason"] == "message.refusal"
    assert res["off_plan_records"] == [], "a refusal is in-plan, not off-plan"

    export_dir = tmp_path / "review" / "smoke" / res["export_dir"].rsplit("/", 1)[1]
    assert len(list((export_dir / "papers").glob("*.md"))) == 5
    info = json.loads((export_dir / "EXPORT_INFO.json").read_text())
    assert info["n_refused_records_excluded"] == 1 and info["n_papers"] == 5
    mapping_path = tmp_path / "review" / "smoke" / "mapping" / res["mapping_path"].rsplit("/", 1)[1]
    entries = json.loads(mapping_path.read_text())["entries"]
    assert target["cache_key"] not in {e["cache_key"] for e in entries}


def test_export_fails_cleanly_when_every_record_was_refused(runs, tmp_path):
    for path in (runs / "smoke" / "records").glob("smoke__*__gpt-4.1__*.json"):
        rec = json.loads(path.read_text())
        rec.update(status="refused", content=None, refusal="no", refusal_reason="message.refusal")
        write_json(path, rec)
    with pytest.raises(review.ReviewError) as exc:
        review.export_anonymized("smoke", runs_dir=runs, review_dir=tmp_path / "review")
    assert "6 refused" in str(exc.value)


def test_unmasked_csv_carries_every_field_the_report_summarises(runs, tmp_path):
    res = review.export_anonymized("smoke", runs_dir=runs, review_dir=tmp_path / "review")
    export_dir = tmp_path / "review" / "smoke" / res["export_dir"].rsplit("/", 1)[1]
    mapping_path = tmp_path / "review" / "smoke" / "mapping" / res["mapping_path"].rsplit("/", 1)[1]
    forms = sorted((export_dir / "forms").glob("*.json"))
    for f in forms:
        form = _fill(json.loads(f.read_text()))
        form["exact_interaction_X4_X5"]["contradictory_statements"] = True
        form["other_second_order_terms"] = [{"term": "X7*X12", "strength": "supported", "quote": "q", "section": "results"}]
        write_json(f, form)
    review.lock_reviews(export_dir)
    out = review.unmask(export_dir, mapping_path)
    header, first = open(out["unmasked_csv"]).read().splitlines()[:2]
    cols = header.split(",")
    assert cols == review._UNMASKED_CSV_COLUMNS
    for needed in ("exact_X4_X5__contradictory", "any_contradictory_statements", "n_other_second_order_terms",
                   "other_second_order_terms_supported",
                   "aux__unsupported_numerical_results_or_claims_of_computation",
                   "aux__numerical_plausibility_of_reported_calculations",
                   "aux__multiplicity_handling_reasonable"):
        assert needed in cols, needed
    row = dict(zip(cols, first.split(",")))
    assert row["exact_X4_X5__contradictory"] == "True" and row["any_contradictory_statements"] == "True"
    assert row["n_other_second_order_terms"] == "1" and row["other_second_order_terms_supported"] == "X7*X12"


def test_aid_separates_product_notation_from_co_mention():
    prod = review.extraction_aid("The product X4*X5 dominates.")
    assert prod["target_terms"]["X4*X5"] and prod["target_term_co_mentions"]["X4*X5"] == []
    words = review.extraction_aid("X4 and X5 are individually uncorrelated with Y.")
    assert words["target_terms"]["X4*X5"] == [], "bare co-mention must not count as product notation"
    assert words["target_term_co_mentions"]["X4*X5"]
    # the generic term list uses the form's spelling, not the numerically sorted one
    assert review.extraction_aid("X5*X19 matters.")["second_order_terms_mentioned"] == ["X19*X5"]


def test_extraction_aid_and_number_check():
    text = ("We find that X4 × X5 is significant (r = 0.28, n = 1000, t = 9.2). X19*X20 may also matter. "
            "X7 squared shows nothing. We applied a Bonferroni correction over 210 tests. The variance of residuals grows with X4.")
    aid = review.extraction_aid(text)
    assert aid["target_terms"]["X4*X5"] and aid["target_terms"]["X19*X20"]
    assert aid["target_terms"]["X4*X20"] == []
    assert "X19*X20" in aid["second_order_terms_mentioned"] and "X7^2" in aid["second_order_terms_mentioned"]
    assert aid["keywords"]["multiple_testing"] and aid["keywords"]["candidate_count"] and aid["keywords"]["heteroscedasticity"]
    chk = review.number_support_check("r = 0.2811 and p = 0.00001 and R^2 = 0.79", "X4*X5  0.2811  1000\nR^2: 0.7889")
    assert "0.00001" in chk["not_found_in_supplied_input"]
    assert chk["n_found_in_supplied_input"] == 2       # 0.2811 exact, 0.79 as 2-dp rounding of 0.7889


def test_empty_form_matches_schema():
    schema = review.load_schema()
    form = review.empty_form(schema, "Pabc123")
    assert form["review_id"] == "Pabc123"
    assert review.validate_form(form, schema)          # empty -> problems listed
    assert set(schema["enums"]["strength"]) == {"absent", "proposed", "supported", "rejected"}


def test_duplicate_record_for_one_scheduled_call_is_refused(runs, tmp_path):
    """Two files claiming one scheduled call would export the paper twice."""
    rec_dir = runs / "smoke" / "records"
    original = sorted(rec_dir.glob("smoke__*__gpt-4.1__*.json"))[0]
    (rec_dir / "smoke__copy__gpt-4.1__rep01__dup.json").write_text(original.read_text())
    with pytest.raises(review.ReviewError) as exc:
        review.export_anonymized("smoke", runs_dir=runs, review_dir=tmp_path / "review")
    assert "same scheduled call" in str(exc.value)


def test_lock_refuses_when_a_form_is_missing(runs, tmp_path):
    """A dropped form would silently shrink every downstream count."""
    res = review.export_anonymized("smoke", runs_dir=runs, review_dir=tmp_path / "review")
    export_dir = tmp_path / "review" / "smoke" / res["export_dir"].rsplit("/", 1)[1]
    forms = sorted((export_dir / "forms").glob("*.json"))
    for f in forms:
        write_json(f, _fill(json.loads(f.read_text())))
    forms[0].unlink()
    with pytest.raises(review.ReviewError) as exc:
        review.lock_reviews(export_dir)
    assert "do not correspond" in str(exc.value)


def test_relocking_changed_forms_is_refused_but_identical_relock_is_a_noop(runs, tmp_path):
    """A lock that can be silently replaced after unmasking guarantees nothing."""
    res = review.export_anonymized("smoke", runs_dir=runs, review_dir=tmp_path / "review")
    export_dir = tmp_path / "review" / "smoke" / res["export_dir"].rsplit("/", 1)[1]
    forms = sorted((export_dir / "forms").glob("*.json"))
    for f in forms:
        write_json(f, _fill(json.loads(f.read_text())))
    lock = review.lock_reviews(export_dir)
    before = json.loads(lock.read_text())

    review.lock_reviews(export_dir)                                  # identical: no-op
    assert json.loads(lock.read_text()) == before

    edited = json.loads(forms[0].read_text())
    edited["exact_interaction_X4_X5"]["strength"] = "supported"      # a post-hoc change
    write_json(forms[0], edited)
    with pytest.raises(review.ReviewError) as exc:
        review.lock_reviews(export_dir)
    assert "refusing to overwrite" in str(exc.value)
    assert json.loads(lock.read_text()) == before, "the original lock must survive"
    assert not review.verify_lock(export_dir)[0]

    review.lock_reviews(export_dir, relock_note="documented pre-unmask correction")
    now = json.loads(lock.read_text())
    assert now["superseded_locks"][0]["created_at"] == before["created_at"]


def test_unmask_refuses_a_form_set_that_does_not_match_the_mapping(runs, tmp_path):
    res = review.export_anonymized("smoke", runs_dir=runs, review_dir=tmp_path / "review")
    export_dir = tmp_path / "review" / "smoke" / res["export_dir"].rsplit("/", 1)[1]
    mapping_path = tmp_path / "review" / "smoke" / "mapping" / res["mapping_path"].rsplit("/", 1)[1]
    forms = sorted((export_dir / "forms").glob("*.json"))
    for f in forms:
        write_json(f, _fill(json.loads(f.read_text())))
    review.lock_reviews(export_dir)
    (export_dir / "papers" / (forms[0].stem + ".md")).unlink()
    with pytest.raises(review.ReviewError) as exc:
        review.unmask(export_dir, mapping_path)
    assert "do not correspond" in str(exc.value)
