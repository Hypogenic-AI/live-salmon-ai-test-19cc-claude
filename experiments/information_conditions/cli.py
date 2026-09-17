#!/usr/bin/env python
"""Command-line entry point for the information-conditions experiment.

Run from anywhere, e.g. from the repository root:
    .venv/bin/python experiments/information_conditions/cli.py generate-inputs
No subcommand makes a network call unless `run --execute` is given.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from infocond.common import load_config, read_json, utc_now  # noqa: E402
from infocond import conditions, data, freeze, manifest as manifest_mod, review, runner  # noqa: E402
from infocond.paths import EXP_DIR, INPUTS_DIR, REPO_ROOT, RUNS_DIR  # noqa: E402


def _bundles(cfg: dict) -> list[dict]:
    data.ensure_full_datasets(cfg)
    data.verify_datasets(cfg)
    return conditions.build_all_bundles(cfg)


def cmd_verify_data(args) -> int:
    cfg = load_config()
    info = data.ensure_full_datasets(cfg)
    ver = data.verify_datasets(cfg)
    print(json.dumps({"datasets": info, "verification": ver}, indent=2))
    return 0


def cmd_generate_inputs(args) -> int:
    cfg = load_config()
    env_problems = manifest_mod.environment_problems(cfg)
    if env_problems:
        print("WARNING: environment differs from the design declared in config.json::environment:", file=sys.stderr)
        for p in env_problems:
            print(f"  - {p}", file=sys.stderr)
        print("  Prompt bytes and/or the generated data may differ. Inputs are still written so they can be "
              "inspected, but `run --execute` will refuse until the environment matches.", file=sys.stderr)
    info = data.ensure_full_datasets(cfg)
    ver = data.verify_datasets(cfg)
    bundles = conditions.build_all_bundles(cfg)
    man = manifest_mod.build_manifest(cfg, bundles, info, ver)
    prov = manifest_mod.build_provenance(cfg, bundles, info, man)
    written = manifest_mod.write_inputs(cfg, bundles, man, prov)
    problems = manifest_mod.verify_written_inputs(man)
    if problems:
        print("ERROR: written inputs do not match manifest:", problems, file=sys.stderr)
        return 2
    print(f"generated {len(written)} files under {INPUTS_DIR.relative_to(REPO_ROOT)} at {utc_now()}")
    for item in man["inputs"]:
        print(f"  {item['dataset']:<12} {item['condition']:<8} chars={item['chars']['combined']:>6} "
              f"est_tokens={item['estimated_input_tokens']:>6} user_sha256={item['hashes']['user_prompt_sha256'][:16]}")
    print(f"  model: {man['model']['key']} -> {man['model']['id']}; request_settings={man['request_settings']}")
    return 0


def cmd_run(args) -> int:
    cfg = load_config()
    bundles = _bundles(cfg)
    model_key = args.model or cfg["model_key"]
    api_key = os.environ.get("OPENROUTER_KEY", "")
    provenance = None
    if args.execute:
        pre = runner.execution_preflight(args.phase, cfg, bundles, api_key, model_key=model_key)
        provenance = {**pre, "git": manifest_mod.git_info(), "executed_at": utc_now()}
        print(f"preflight ok: freeze {pre['freeze']['freeze_file']} (design {pre['freeze']['design_hash'][:12]})")
    else:
        ok, reason, _ = freeze.verify_freeze(args.phase)
        print(f"dry-run (no calls). freeze status for phase {args.phase!r}: {'OK' if ok else 'NOT READY'} - {reason}")
    summary = runner.run_phase(args.phase, cfg, bundles, execute=args.execute, runs_dir=RUNS_DIR, model_key=model_key,
                               api_key=api_key, retry_failed=args.retry_failed, provenance=provenance)
    keys = ("phase", "executed", "model_id", "planned", "already_cached_success", "already_cached_refused",
            "skipped_failed", "called", "success", "refused", "failed", "truncated", "model_mismatch")
    print(json.dumps({k: summary[k] for k in keys}, indent=2))
    for row in summary["records"]:
        print(f"  #{row['schedule_index']:>2} {row['dataset']:<12} {row['condition']:<8} rep{row['rep']} {row['state']}"
              + (" TRUNCATED" if row.get("truncated") else "")
              + (f" REFUSED ({row['refusal_reason']})" if row.get("refusal_reason") else ""))
    if summary["refused"]:
        print(f"\n{summary['refused']} explicit refusal(s): recorded in full, never retried, and never exported "
              f"as papers for scoring. See runs/{args.phase}/summary.json::refusals.", file=sys.stderr)
    return 0 if summary["failed"] == 0 else 1


def cmd_freeze(args) -> int:
    path = freeze.create_freeze(args.phase, args.note, allow_dirty=args.allow_dirty)
    rec = read_json(path)
    print(f"freeze written: {path.relative_to(EXP_DIR)}  design_hash={rec['design_hash'][:16]}  git_head={rec['git_head'][:12]}")
    print(f"Next: commit the freeze file, then `run --phase {args.phase} --execute`.")
    return 0


def cmd_verify_freeze(args) -> int:
    ok, reason, _ = freeze.verify_freeze(args.phase)
    print(("OK: " if ok else "NOT READY: ") + reason)
    return 0 if ok else 1


def cmd_export_review(args) -> int:
    res = review.export_anonymized(args.phase)
    print(json.dumps(res, indent=2))
    refused = res.get("refused_records") or []
    if refused:
        print(f"\n{len(refused)} scheduled call(s) ended in an explicit refusal and were NOT exported as papers:",
              file=sys.stderr)
        for row in refused:
            print(f"  - {row['record_file']} ({row['refusal_reason']})", file=sys.stderr)
        print("  They stay in runs/<phase>/records/ and in the phase summary; report them alongside failures "
              "and truncations rather than scoring them.", file=sys.stderr)
    off_plan = res.get("off_plan_records") or []
    if off_plan:
        print(f"\nWARNING: {len(off_plan)} success record(s) in runs/{args.phase}/records/ are NOT in the "
              f"current runs/{args.phase}/schedule.json and were NOT exported:", file=sys.stderr)
        for row in off_plan:
            print(f"  - {row['record_file']} (cache_key={row['cache_key']}, prompt_hash={row['prompt_hash'][:16]})",
                  file=sys.stderr)
        print("  These are usually left over from a superseded prompt or request setting. Move them aside "
              "and record the reason in CHANGES.md before scoring.", file=sys.stderr)
    return 0


def cmd_extract_aid(args) -> int:
    export_dir = Path(args.export_dir)
    aid_dir = export_dir / "aid"
    aid_dir.mkdir(exist_ok=True)
    n = 0
    for p in sorted((export_dir / "papers").glob("*.md")):
        aid = review.extraction_aid(p.read_text())
        (aid_dir / f"{p.stem}.json").write_text(json.dumps(aid, indent=2, ensure_ascii=False) + "\n")
        n += 1
    print(f"wrote {n} aid files to {aid_dir}")
    return 0


def cmd_lock_reviews(args) -> int:
    print(f"lock written: {review.lock_reviews(Path(args.export_dir), allow_incomplete=args.allow_incomplete, relock_note=args.relock_note)}")
    return 0


def cmd_unmask(args) -> int:
    print(json.dumps(review.unmask(Path(args.export_dir), Path(args.mapping), inputs_dir=INPUTS_DIR), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cli.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify-data", help="regenerate gitignored full CSVs if missing; verify against committed samples/baselines").set_defaults(fn=cmd_verify_data)
    sub.add_parser("generate-inputs", help="write the six model inputs + manifest (no API calls)").set_defaults(fn=cmd_generate_inputs)
    r = sub.add_parser("run", help="dry-run by default; --execute makes real calls")
    r.add_argument("--phase", choices=["smoke", "formal"], required=True)
    r.add_argument("--execute", action="store_true", help="make real API calls (requires OPENROUTER_KEY and a valid freeze)")
    r.add_argument("--model", default=None,
                   help="model key from upstream MODELS, for previewing a dry-run schedule only; --execute "
                        "refuses anything other than config.json model_key (change the config and re-freeze)")
    r.add_argument("--retry-failed", action="store_true", help="re-attempt records whose previous attempts all failed technically")
    r.set_defaults(fn=cmd_run)
    f = sub.add_parser("freeze", help="record a design freeze for a phase")
    f.add_argument("--phase", choices=["smoke", "formal"], required=True)
    f.add_argument("--note", required=True, help="why this freeze is being created")
    f.add_argument("--allow-dirty", action="store_true")
    f.set_defaults(fn=cmd_freeze)
    vf = sub.add_parser("verify-freeze", help="check the latest freeze for a phase against the working tree")
    vf.add_argument("--phase", choices=["smoke", "formal"], required=True)
    vf.set_defaults(fn=cmd_verify_freeze)
    e = sub.add_parser("export-review", help="label-hidden export of successful papers for human review")
    e.add_argument("--phase", choices=["smoke", "formal"], required=True)
    e.set_defaults(fn=cmd_export_review)
    a = sub.add_parser("extract-aid", help="regex pointers for reviewers (no model calls)")
    a.add_argument("--export-dir", required=True)
    a.set_defaults(fn=cmd_extract_aid)
    lk = sub.add_parser("lock-reviews", help="hash filled review forms before unmasking")
    lk.add_argument("--export-dir", required=True)
    lk.add_argument("--allow-incomplete", action="store_true")
    lk.add_argument("--relock-note", default=None, help="required to replace an existing lock whose forms have changed")
    lk.set_defaults(fn=cmd_lock_reviews)
    u = sub.add_parser("unmask", help="join locked reviews with the hidden mapping")
    u.add_argument("--export-dir", required=True)
    u.add_argument("--mapping", required=True)
    u.set_defaults(fn=cmd_unmask)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
