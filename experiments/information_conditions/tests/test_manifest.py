"""The design record must be reproducible; the environment record must not be.

inputs/manifest.json is covered by the design hash, so anything in it that depends
on the clone, the commit or the machine would make a freeze fail for reasons that
have nothing to do with the experiment.  inputs/provenance.json is where that
information belongs.
"""
import json

import pytest

from infocond import data, manifest as manifest_mod
from infocond.common import canonical_json
from infocond.paths import EXP_DIR

VOLATILE_KEYS = ("head_commit", "working_tree_dirty", "origin_url", "branch",
                 "regenerated_now", "platform", "generated_at")


@pytest.fixture(scope="module")
def built(cfg, datasets_ready, bundles):
    info = data.ensure_full_datasets(cfg)
    return manifest_mod.build_manifest(cfg, bundles, info, datasets_ready), info


def test_manifest_is_identical_across_git_states_and_regeneration(cfg, bundles, datasets_ready, monkeypatch, built):
    man, info = built
    monkeypatch.setattr(manifest_mod, "git_info",
                        lambda: {"head_commit": "0" * 40, "branch": "somewhere-else",
                                 "working_tree_dirty": True, "origin_url": "git@example.invalid:x.git"})
    fresh_clone_info = {k: {**v, "regenerated_now": True} for k, v in info.items()}
    again = manifest_mod.build_manifest(cfg, bundles, fresh_clone_info, datasets_ready)
    assert canonical_json(again) == canonical_json(man), (
        "the manifest changed with git state or with whether the gitignored CSVs "
        "happened to be regenerated; that would invalidate a freeze for no reason")


def test_manifest_carries_no_machine_or_checkout_state(built):
    man, _ = built
    blob = canonical_json(man)
    for key in VOLATILE_KEYS:
        assert f'"{key}"' not in blob, f"{key} must live in provenance.json, not the manifest"
    # but the dataset *content* identity is still there
    assert man["dataset_verification"]["live_salmon"]["full_csv_sha256"]
    assert man["required_environment"]["required_packages"] == {"numpy": "2.4.3", "pandas": "3.0.1"}


def test_provenance_carries_the_volatile_state(cfg, bundles, datasets_ready, built):
    man, info = built
    prov = manifest_mod.build_provenance(cfg, bundles, info, man)
    assert set(prov["git"]) == {"head_commit", "branch", "working_tree_dirty", "origin_url"}
    assert "platform" in prov["observed_package_versions"]
    assert set(prov["datasets_regenerated_now"]) == set(cfg["datasets"])
    assert prov["environment_problems"] == []


def _num_diffs(a, b, path="", tol=1e-9):
    """Structural comparison that tolerates last-ulp float drift."""
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in set(a) | set(b):
            if k not in a or k not in b:
                out.append(f"{path}.{k}: present in only one")
            else:
                out += _num_diffs(a[k], b[k], f"{path}.{k}", tol)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} vs {len(b)}")
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                out += _num_diffs(x, y, f"{path}[{i}]", tol)
    elif isinstance(a, float) or isinstance(b, float):
        if abs(float(a) - float(b)) > tol:
            out.append(f"{path}: {a} vs {b}")
    elif a != b:
        out.append(f"{path}: {a!r} vs {b!r}")
    return out


def compare_committed_manifest(on_disk, fresh):
    """Compare a committed manifest with a fresh build, according to its own format.

    v1 stored raw float64 from numpy linear algebra, which drifts in the last ulp
    between BLAS builds, so a v1 record can only be compared numerically -- and it has
    no version key, so the fresh build's key is dropped for the comparison.  v2 rounds
    every float, so it must match exactly, version key included.  Reading the version
    off the file rather than always stripping it is what makes the check keep working
    after `generate-inputs` writes a v2 record.
    """
    version = on_disk.get("manifest_format_version", 1)
    if version == 1:
        return version, _num_diffs(on_disk, {k: v for k, v in fresh.items()
                                             if k != "manifest_format_version"})
    if canonical_json(on_disk) == canonical_json(fresh):
        return version, []
    return version, _num_diffs(on_disk, fresh, tol=0.0) or ["byte difference with no structural diff"]


def test_committed_manifest_matches_a_fresh_build(built):
    """Guards the committed artefact itself, not just the builder."""
    man, _ = built
    on_disk = json.loads((EXP_DIR / "inputs" / "manifest.json").read_text())
    version, diffs = compare_committed_manifest(on_disk, man)
    assert not diffs, (f"committed manifest is format v{version}; run `cli.py generate-inputs`. "
                       "diffs: " + "; ".join(diffs[:8]))


def test_comparison_is_strict_for_v2_and_tolerant_for_v1(built):
    """Regression for the version-aware comparison itself.

    After `generate-inputs` writes a v2 record the committed file carries the version
    key, and the old comparison -- which always stripped that key from the fresh build --
    reported `.manifest_format_version: present in only one` and failed.  A v2 record
    must compare strictly and keep the key; a v1 record must still be tolerated.
    """
    man, _ = built

    # a freshly written v2 record round-trips exactly, version key and all
    v2_on_disk = json.loads(json.dumps(man))
    version, diffs = compare_committed_manifest(v2_on_disk, man)
    assert version == 2 and not diffs

    # v2 is strict: last-ulp drift that v1 tolerates must now be caught
    drifted = json.loads(json.dumps(man))
    drifted["dataset_verification"]["live_salmon"]["corr_with_y_max_abs_diff_vs_baseline_4dp"] = 1e-13
    assert compare_committed_manifest(drifted, man)[1], "v2 comparison must not tolerate float drift"

    # v1 has no version key and is compared numerically
    v1_on_disk = {k: v for k, v in json.loads(json.dumps(man)).items() if k != "manifest_format_version"}
    version, diffs = compare_committed_manifest(v1_on_disk, man)
    assert version == 1 and not diffs


def test_manifest_floats_are_normalised(built):
    """No float in the design record may carry more precision than the format allows.

    This is what makes the record byte-reproducible across machines: unrounded float64
    from lstsq/corrcoef differs in the last digit between platforms, and that difference
    used to reach the design hash and invalidate a freeze for no reason.
    """
    from infocond.manifest import MANIFEST_FLOAT_DECIMALS, MANIFEST_FORMAT_VERSION
    man, _ = built
    assert man["manifest_format_version"] == MANIFEST_FORMAT_VERSION
    bad = []
    def walk(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items(): walk(v, f"{path}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o): walk(v, f"{path}[{i}]")
        elif isinstance(o, float) and o != round(o, MANIFEST_FLOAT_DECIMALS):
            bad.append(path)
    walk(man)
    assert not bad, f"unrounded floats reach the design record: {bad[:5]}"


def test_normalise_floats_absorbs_last_ulp_drift():
    from infocond.manifest import normalise_floats
    a = {"r": -0.028491680456637882, "n": 1000, "z": -0.0, "xs": [0.1 + 0.2]}
    b = {"r": -0.028491680456637872, "n": 1000, "z": 0.0, "xs": [0.30000000000000004]}
    assert canonical_json(normalise_floats(a)) == canonical_json(normalise_floats(b))
    assert normalise_floats(-0.0) == 0.0


def test_environment_contract_is_checked(cfg):
    assert manifest_mod.environment_problems(cfg) == [], "this checkout does not match config.json::environment"
    bad = {**cfg, "environment": {"python_minor": "2.7", "required_packages": {"numpy": "0.0.1"}}}
    problems = manifest_mod.environment_problems(bad)
    assert len(problems) == 2 and any("numpy" in p for p in problems) and any("python" in p for p in problems)
