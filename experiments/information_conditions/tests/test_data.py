"""Regenerated full CSVs must equal what upstream used."""
from infocond import data
from infocond.paths import REPO_ROOT


def test_full_csv_head_equals_committed_sample(cfg, datasets_ready):
    for name in ("live_salmon", "dead_salmon"):
        assert datasets_ready[name]["head10_matches_committed_sample"] is True
        assert datasets_ready[name]["n_rows"] == 1000


def test_baseline_statistics_match(datasets_ready):
    for name in ("live_salmon", "dead_salmon"):
        assert datasets_ready[name]["ols_r2_matches_baseline"] is True
        assert datasets_ready[name]["corr_with_y_max_abs_diff_vs_baseline_4dp"] == 0.0


def test_in_memory_regeneration_is_deterministic():
    a = data.regenerate_in_memory()
    b = data.regenerate_in_memory()
    for k in a:
        assert a[k].equals(b[k])


def test_ensure_does_not_rewrite_existing(cfg, datasets_ready):
    before = {n: data.dataset_path(cfg, n).stat().st_mtime_ns for n in cfg["datasets"]}
    info = data.ensure_full_datasets(cfg)
    assert all(not v["regenerated_now"] for v in info.values())
    after = {n: data.dataset_path(cfg, n).stat().st_mtime_ns for n in cfg["datasets"]}
    assert before == after


def test_committed_files_untouched_by_module(cfg):
    # committed sample files keep their upstream hashes
    from infocond.common import sha256_file
    assert sha256_file(REPO_ROOT / "datasets/live_salmon_sample.csv") == "3969aebcf86882d12c3caff6eac0c284b85b16ebdb2797930cb5b1cbe0bc0024"
    assert sha256_file(REPO_ROOT / "datasets/dead_salmon_sample.csv") == "7ae6f6ef2868fd3fb9de01491b399fd731c93061ac65df71f07d67887c67afce"
    assert sha256_file(REPO_ROOT / "datasets/generate_live_salmon_data.py") == "8a99f1a00fe61f8de1aaad0eec12b30665a72a88877feb35688849fb04e225d7"


def test_one_present_one_missing_leaves_the_present_file_alone(cfg, tmp_path, monkeypatch):
    """regenerate_in_memory() always returns both frames because the two datasets share one
    RNG stream.  Writing both whenever either is absent would silently replace a file that
    is already on disk, destroying the very difference verify_datasets exists to catch."""
    from infocond import data as D
    ds = tmp_path / "datasets"
    ds.mkdir()
    monkeypatch.setattr(D, "REPO_ROOT", tmp_path)

    present = D.dataset_path(cfg, "live_salmon")
    present.parent.mkdir(parents=True, exist_ok=True)
    sentinel = "SENTINEL,DO,NOT,OVERWRITE\n"
    present.write_text(sentinel)
    absent = D.dataset_path(cfg, "dead_salmon")
    assert not absent.exists()

    info = D.ensure_full_datasets(cfg)

    assert present.read_text() == sentinel, "an existing dataset file must not be rewritten"
    assert absent.exists() and len(absent.read_text().splitlines()) == 1001
    assert info["live_salmon"]["regenerated_now"] is False
    assert info["dead_salmon"]["regenerated_now"] is True


def test_both_missing_writes_both_and_both_present_writes_neither(cfg, tmp_path, monkeypatch):
    from infocond import data as D
    (tmp_path / "datasets").mkdir()
    monkeypatch.setattr(D, "REPO_ROOT", tmp_path)

    info = D.ensure_full_datasets(cfg)
    assert all(v["regenerated_now"] for v in info.values())
    stamps = {n: D.dataset_path(cfg, n).stat().st_mtime_ns for n in cfg["datasets"]}

    info2 = D.ensure_full_datasets(cfg)
    assert not any(v["regenerated_now"] for v in info2.values())
    assert {n: D.dataset_path(cfg, n).stat().st_mtime_ns for n in cfg["datasets"]} == stamps

