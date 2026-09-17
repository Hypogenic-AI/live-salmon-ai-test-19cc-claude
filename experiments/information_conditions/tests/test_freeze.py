import shutil

import pytest

from infocond import freeze
from infocond.paths import EXP_DIR


@pytest.fixture
def design_copy(tmp_path):
    dst = tmp_path / "exp"
    dst.mkdir()
    (dst / "REPORT.md").write_text((EXP_DIR / "REPORT.md").read_text())
    for pattern in freeze.DESIGN_GLOBS:
        for p in EXP_DIR.glob(pattern):
            if p.is_file():
                (dst / p.relative_to(EXP_DIR)).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(p, dst / p.relative_to(EXP_DIR))
    return dst


def test_design_hash_covers_cli_and_report_template_but_not_provenance_or_report():
    """What the freeze promises to cover, asserted directly on the real experiment dir."""
    files = freeze.design_file_hashes(EXP_DIR)
    for must in ("cli.py", "config.json", "RUBRIC.md", "review_schema.json", "review_template.md",
                 "report_template.md", "inputs/manifest.json", "infocond/runner.py", "infocond/review.py"):
        assert must in files, f"{must} must be covered by the design hash"
    for must_not, why in (("inputs/provenance.json", "environment record: cloning or committing must not invalidate a freeze"),
                          ("REPORT.md", "working report: writing up results is not a design change")):
        assert must_not not in files, f"{must_not} must stay out of the design hash ({why})"


def test_cli_change_invalidates_a_freeze(design_copy, tmp_path, monkeypatch):
    monkeypatch.setattr(freeze, "experiment_dirty_paths", lambda exp_dir=None: [])
    fz = tmp_path / "freezes"
    freeze.create_freeze("smoke", "initial design", exp_dir=design_copy, freezes_dir=fz)
    assert freeze.verify_freeze("smoke", design_copy, fz)[0]
    cli = design_copy / "cli.py"
    cli.write_text(cli.read_text() + "\n# post-freeze behavioural change\n")
    ok, reason, _ = freeze.verify_freeze("smoke", design_copy, fz)
    assert not ok and "cli.py" in reason


def test_report_and_provenance_changes_do_not_invalidate_a_freeze(design_copy, tmp_path, monkeypatch):
    monkeypatch.setattr(freeze, "experiment_dirty_paths", lambda exp_dir=None: [])
    fz = tmp_path / "freezes"
    freeze.create_freeze("smoke", "initial design", exp_dir=design_copy, freezes_dir=fz)
    (design_copy / "REPORT.md").write_text("# filled in after unmasking\n| live_salmon | B | 5 | 5 | 0 | 0 | 0 |\n")
    (design_copy / "inputs").mkdir(exist_ok=True)
    (design_copy / "inputs" / "provenance.json").write_text('{"git": {"head_commit": "deadbeef"}}')
    ok, reason, _ = freeze.verify_freeze("smoke", design_copy, fz)
    assert ok, reason


def test_design_hash_changes_when_any_design_file_changes(design_copy):
    h0 = freeze.design_hash(design_copy)
    assert h0 == freeze.design_hash(design_copy)
    (design_copy / "config.json").write_text((design_copy / "config.json").read_text() + "\n")
    assert freeze.design_hash(design_copy) != h0


def test_freeze_verify_roundtrip_and_invalidation(design_copy, tmp_path, monkeypatch):
    monkeypatch.setattr(freeze, "experiment_dirty_paths", lambda exp_dir=None: [])
    fz = tmp_path / "freezes"
    ok, reason, _ = freeze.verify_freeze("smoke", design_copy, fz)
    assert not ok and "no freeze record" in reason
    with pytest.raises(freeze.FreezeError):
        freeze.create_freeze("smoke", "", exp_dir=design_copy, freezes_dir=fz)
    path = freeze.create_freeze("smoke", "initial design", exp_dir=design_copy, freezes_dir=fz)
    assert path.exists()
    ok, reason, rec = freeze.verify_freeze("smoke", design_copy, fz)
    assert ok and rec["note"] == "initial design" and rec["git_head"]
    # formal has its own freeze requirement
    ok_f, reason_f, _ = freeze.verify_freeze("formal", design_copy, fz)
    assert not ok_f
    # a smoke-stage fix invalidates the freeze until a new one is created
    code = design_copy / "infocond" / "runner.py"
    code.write_text(code.read_text() + "\n# fix\n")
    ok2, reason2, _ = freeze.verify_freeze("smoke", design_copy, fz)
    assert not ok2 and "infocond/runner.py" in reason2
    freeze.create_freeze("formal", "post-smoke fix", exp_dir=design_copy, freezes_dir=fz)
    ok3, _, _ = freeze.verify_freeze("formal", design_copy, fz)
    assert ok3


def test_dirty_tree_blocks_freeze(design_copy, tmp_path, monkeypatch):
    monkeypatch.setattr(freeze, "experiment_dirty_paths", lambda exp_dir=None: ["experiments/information_conditions/config.json"])
    with pytest.raises(freeze.FreezeError):
        freeze.create_freeze("smoke", "x", exp_dir=design_copy, freezes_dir=tmp_path / "f")
    p = freeze.create_freeze("smoke", "x", allow_dirty=True, exp_dir=design_copy, freezes_dir=tmp_path / "f")
    assert freeze.latest_freeze("smoke", tmp_path / "f")[1]["dirty_design_paths_at_freeze"]
    assert p.exists()
