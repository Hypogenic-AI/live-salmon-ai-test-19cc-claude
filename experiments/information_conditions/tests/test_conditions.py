import re

import pytest

from infocond import conditions, upstream
from infocond.data import dataset_path


def test_condition_A_equals_upstream_summary(cfg, by_key):
    for ds in ("live_salmon", "dead_salmon"):
        expected = upstream.prepare_summary(str(dataset_path(cfg, ds)), cfg["datasets"][ds]["label"])
        assert by_key[(ds, "A")]["summary"] == expected
        assert expected.startswith(f"# Dataset: {cfg['datasets'][ds]['label']}")


def test_dataset_labels_are_the_upstream_neutral_labels(cfg):
    assert cfg["datasets"]["live_salmon"]["label"] == "Research Dataset A"
    assert cfg["datasets"]["dead_salmon"]["label"] == "Research Dataset B"


def test_conditions_nest(by_key):
    for ds in ("live_salmon", "dead_salmon"):
        a, ap, b = (by_key[(ds, c)]["summary"] for c in ("A", "A_prime", "B"))
        assert ap.startswith(a) and len(ap) > len(a)
        assert b.startswith(ap) and len(b) > len(ap)
        assert "Part 1" in ap and "Part 2" not in ap
        assert "Part 2" in b


def test_prompts_use_upstream_system_and_template(by_key):
    sys_prompt = upstream.system_prompt()
    tmpl = upstream.user_prompt_template()
    for b in by_key.values():
        assert b["system_prompt"] == sys_prompt
        assert b["user_prompt"] == tmpl.format(data_summary=b["summary"])


def test_a_prime_content(by_key):
    b = by_key[("live_salmon", "A_prime")]
    s = b["summary"]
    assert b["details"]["n_residual_diagnostics"] == 20
    assert "n = 1000" in s and "In-sample R^2" in s
    assert "0.7889" in s  # committed baseline OLS R^2 for the live data
    rows = re.findall(r"^X\d+\s+-?\d\.\d{4}\s+1000$", s.split("Table 1.")[1], flags=re.M)
    assert len(rows) == 20
    # no fitted coefficients anywhere in the appended text
    appended = s[len(by_key[("live_salmon", "A")]["summary"]):]
    for name, coef in b["_private_details"]["_fitted_coefficients_not_in_prompt"].items():
        assert f"{coef:.4f}" not in appended, f"coefficient for {name} leaked"
    assert "coefficient" in appended.lower() and "not supplied" in appended.lower()
    assert "precomputed" in appended.lower()


def test_b_content(by_key):
    b = by_key[("live_salmon", "B")]
    d = b["details"]
    assert d["n_second_order_terms"] == 210 and d["n_squares"] == 20 and d["n_cross_products"] == 190
    part2 = b["summary"].split("Table 2.")[1]
    rows = re.findall(r"^(X\d+(?:\^2|\*X\d+))\s+(-?\d\.\d{4})\s+(1000)$", part2, flags=re.M)
    assert len(rows) == 210
    names = [r[0] for r in rows]
    assert names[:3] == ["X1^2", "X1*X2", "X1*X3"] and names[-1] == "X20^2" and len(set(names)) == 210
    # fixed index ordering, not sorted by r
    rs = [float(r[1]) for r in rows]
    assert rs != sorted(rs) and rs != sorted(rs, reverse=True)
    # nothing that looks like a p-value, star, or correction
    assert not re.search(r"p\s*[<=>]\s*0\.\d", part2) and "*" not in part2.replace("*X", "")
    assert not re.search(r"bonferroni|significant|p-value|adjust", part2, re.I)


def test_no_answer_key_or_labels_in_any_prompt(bundles):
    for b in bundles:
        text = b["system_prompt"] + "\n" + b["user_prompt"]
        assert conditions.forbidden_content_hits(text) == []
        low = text.lower()
        for bad in ("salmon", "live", "dead", "ground truth", "0.8*(x4", "2*x1", "= 2*x1", "true model"):
            assert not re.search(r"(?<![a-z0-9.])" + re.escape(bad) + r"(?![a-z0-9])", low), bad


def test_forbidden_detector_catches_formula_variants():
    hits = conditions.forbidden_content_hits
    assert hits("Y = 2*X1 + 0.5*X2 - 1.5*X3 + 0.8*(X4*X5) + epsilon")
    assert hits("2.0·X1") and hits("0.8 * (X4 × X5)") and hits("salmon") and hits("Research on dead_salmon")
    assert hits("X12*X13   0.0123   1000") == []
    assert hits("X4*X5   0.2811   1000") == []


def test_deterministic_rebuild(cfg, bundles):
    again = conditions.build_all_bundles(cfg)
    for x, y in zip(bundles, again):
        assert x["user_prompt"] == y["user_prompt"]
        assert x["hashes"] == y["hashes"]


def test_input_length_check(cfg, by_key):
    b = by_key[("live_salmon", "B")]
    res = conditions.check_input_length(b, cfg)
    assert res["ok"] and res["estimated_input_tokens"] == b["estimated_input_tokens"]
    tiny = {**cfg, "input_length": {**cfg["input_length"], "max_estimated_input_tokens": 10}}
    with pytest.raises(conditions.InputTooLong):
        conditions.check_input_length(b, tiny)
    assert conditions.estimate_tokens("abcd" * 10, 1.8) == 23


def test_unknown_condition_rejected(cfg):
    with pytest.raises(ValueError):
        conditions.build_summary("C", str(dataset_path(cfg, "live_salmon")), "x", 4)
