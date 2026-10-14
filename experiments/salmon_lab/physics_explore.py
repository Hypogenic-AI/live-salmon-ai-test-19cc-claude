"""
Put a model in the physics lab and let it collect its own data.

Each turn the model may run experiments and Python code on the data it has collected; it
then sees the new runs and the output. The episode ends when it writes its paper or runs
out of turns. It then submits its law as a Python function, which is run in the sandbox on
experiments it has not seen.

Conditions: base; stated_error, where the briefing gives the size of the measurement error;
kappa2, where the new law is about seven times stronger; kappa2_stated_error, both at once;
kappa0 and kappa0_stated_error, the same laboratory without the new law.

Dry run by default: a scripted stand-in plays the model's part, no API calls (the sandbox
is used, so Docker must be running). Pass --execute to call the API.
"""

import argparse
import json
from datetime import datetime, timezone

import httpx

import physics_prompts as P
import physics_world as pw
import sandbox
from explore import (
    BUDGET, DRY_RUN_DIR, MAX_TURNS, MODELS, PER_TURN, RESULTS_DIR, Stopped, call, extract, load_api_key,
    parse_json_array, python_blocks, save_partial, scripted, strip_fences, total_cost, write_transcript,
)
from prompts import render_python

DISPLAY = ["run", *pw.OBJECT, *pw.LAUNCH, *pw.MEASURED]
STATED_ERROR = P.ERROR_STATED.format(time=pw.TIME_NOISE, relative=pw.RELATIVE_NOISE)
CONDITIONS = {
    "base": {"kappa": pw.KAPPA, "measurement_error": P.ERROR_UNSTATED},
    "stated_error": {"kappa": pw.KAPPA, "measurement_error": STATED_ERROR},
    "kappa2": {"kappa": 2.0, "measurement_error": P.ERROR_UNSTATED},
    "kappa2_stated_error": {"kappa": 2.0, "measurement_error": STATED_ERROR},
    "kappa0": {"kappa": 0.0, "measurement_error": P.ERROR_UNSTATED},
    "kappa0_stated_error": {"kappa": 0.0, "measurement_error": STATED_ERROR},
}


def opening_messages(measurement_error):
    briefing = P.BRIEFING.format(budget=BUDGET, per_turn=PER_TURN, max_turns=MAX_TURNS, measurement_error=measurement_error,
                                 max_output=sandbox.MAX_OUTPUT, timeout=sandbox.TIMEOUT)
    return [{"role": "system", "content": P.SYSTEM}, {"role": "user", "content": briefing}]


def carry_out(lab, text, turn, run_code):
    """Run a reply's experiments, then its code. Returns (feedback for the model, record)."""
    record = {"turn": turn}
    raw, blocks = extract("experiments", text), python_blocks(text)
    if raw is None and not blocks:
        record["error"] = "no tags"
        parts = [P.NO_TAGS]
    else:
        parts = []
        if raw is not None:
            try:
                specs = parse_json_array(raw)
            except (ValueError, json.JSONDecodeError) as err:
                parts.append(P.BAD_JSON.format(error=err))
                record["experiments_error"] = str(err)
            else:
                rows, messages = lab.run_experiments(specs)
                record.update(experiments=specs, new_runs=len(rows), refused=messages)
                if rows:
                    parts.append("<runs>\n" + P.render_runs(rows, DISPLAY, pw.describe) + "\n</runs>")
                parts += messages
        if blocks:
            ran = [{"code": code, **run_code(code, *lab.code_table())} for code in blocks]
            record["python"] = ran
            rendered = [render_python(k, r, sandbox.MAX_OUTPUT) for k, r in enumerate(ran, 1)]
            parts.append("<python_output>\n" + "\n\n".join(rendered) + "\n</python_output>")
    record["runs_so_far"] = len(lab.rows)
    if lab.runs_left() == 0:
        parts.append(P.NO_RUNS_LEFT)
    parts.append(P.STATUS.format(used=len(lab.rows), budget=BUDGET, turn=turn, max_turns=MAX_TURNS))
    return "\n\n".join(parts), record


def run_episode(seed, respond, condition="base", run_code=sandbox.run_code):
    """respond(messages) -> {"content", "finish_reason", "returned_model", "usage"}."""
    kappa = CONDITIONS[condition]["kappa"]
    lab = pw.PhysicsLab(seed, kappa=kappa, run_budget=BUDGET, max_runs_per_turn=PER_TURN)
    messages = opening_messages(CONDITIONS[condition]["measurement_error"])
    calls, turns = [], []
    report, report_turn = None, None

    def ask():
        try:
            r = respond(messages)
        except Exception as err:
            state = {"turns": turns, "rows": lab.rows, "calls": calls, "messages": messages}
            raise Stopped(f"{type(err).__name__}: {err}", state) from err
        calls.append({k: r.get(k) for k in ("finish_reason", "returned_model", "usage", "reasoning")})
        messages.append({"role": "assistant", "content": r["content"]})
        if r["finish_reason"] != "stop":
            print(f"    warning: finish_reason={r['finish_reason']}")
        return r["content"]

    for turn in range(1, MAX_TURNS + 1):
        text = ask()
        report = extract("report", text)
        if report is not None:
            report_turn = turn
            break
        feedback, record = carry_out(lab, text, turn, run_code)
        if turn == MAX_TURNS:
            feedback += "\n\n" + P.OUT_OF_TURNS.format(max_turns=MAX_TURNS)
        turns.append(record)
        messages.append({"role": "user", "content": feedback})
        print(f"    turn {turn}: {record.get('new_runs', 0)} new runs, {len(record.get('python', []))} code blocks"
              f"{' (' + record['error'] + ')' if 'error' in record else ''}")

    report_without_tags = False
    if report is None:
        text = ask()
        report = extract("report", text)
        if report is None:
            report, report_without_tags = text, True

    cases = pw.law_tests()
    messages.append({"role": "user", "content": P.LAW.format(n=len(cases))})
    law = extract("law", ask())
    law = strip_fences(law) if law else None
    law_run, predictions = None, None
    if law:
        law_run = run_code(pw.law_program(law, cases), pw.COLUMNS, [])
        predictions = pw.law_predictions(law_run["output"])

    return {
        "seed": seed,
        "world": "physics",
        "condition": condition,
        "kappa": kappa,
        "budget": BUDGET,
        "per_turn": PER_TURN,
        "max_turns": MAX_TURNS,
        "report": report,
        "report_turn": report_turn,
        "report_without_tags": report_without_tags,
        "law": law,
        "law_run": law_run,
        "law_cases": cases,
        "law_predictions": predictions,
        "turns": turns,
        "rows": lab.rows,
        "calls": calls,
        "cost": total_cost(calls),
        "messages": messages,
    }


SCRIPTED_REPLIES = [
    '<experiments>[{"n": 100}]</experiments>\n'
    '<python>print(df.shape)\nprint(df.groupby("shape")["flight_time"].mean().round(3))</python>',
    '<experiments>[{"object": {"mass": 2, "shape": "cube"}, "launch": {"height": 30, "air_density": 0}, "n": 10}, '
    '{"object": {"shape": "pyramid"}}]</experiments>\n'
    '<python>vac = df[df.air_density == 0]\nprint((2 * vac.height / vac.flight_time**2).describe().round(3))</python>',
    '<report>Title: (scripted stand-in, not a model)\n\nAbstract: ...</report>',
    '<law>\nimport math\n\ndef predict(obj, launch):\n    g = 9.81\n'
    '    h, v, a = launch["height"], launch["speed"], math.radians(launch["angle"])\n'
    '    vy, vx = v * math.sin(a), v * math.cos(a)\n    t = (vy + math.sqrt(vy * vy + 2 * g * h)) / g\n'
    '    return {"flight_time": t, "distance": vx * t, "impact_speed": math.hypot(vx, vy - g * t)}\n</law>',
]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--execute", action="store_true", help="make real API calls")
    p.add_argument("--model", default="claude-sonnet-5.5", choices=list(MODELS))
    p.add_argument("--condition", default="base", choices=list(CONDITIONS))
    p.add_argument("--runs", type=int, default=1)
    args = p.parse_args()

    if not sandbox.available():
        raise SystemExit("The physics lab needs Docker running and the sandbox image built (see sandbox.py).")
    if not args.execute:
        episode = run_episode(seed=0, respond=scripted(SCRIPTED_REPLIES), condition=args.condition)
        DRY_RUN_DIR.mkdir(exist_ok=True)
        name = f"physics_{args.condition}"
        (DRY_RUN_DIR / f"{name}_episode.json").write_text(json.dumps(episode, indent=2))
        write_transcript(episode, DRY_RUN_DIR / f"{name}_transcript.md")
        print(f"DRY RUN: no API calls. Transcript written to dry_run/{name}_transcript.md.")
        print(f"Would run {args.runs} episode(s) with {args.model} in condition {args.condition}. Re-run with --execute.")
        return

    key = load_api_key()
    if not key:
        raise SystemExit("OPENROUTER_API_KEY not found in the environment or in .env at the repo root.")
    with httpx.Client() as client:
        for run in range(1, args.runs + 1):
            out = RESULTS_DIR / "physics" / args.condition / args.model / f"run{run}.json"
            if out.exists():
                print(f"{out.relative_to(RESULTS_DIR.parent)} exists, skipping")
                continue
            print(f"physics / {args.condition} / {args.model} / run {run}")
            started = datetime.now(timezone.utc).isoformat()
            try:
                episode = run_episode(run, lambda messages: call(client, key, args.model, messages), args.condition)
            except Stopped as stop:
                partial = out.with_name(f"run{run}.partial.json")
                save_partial(partial, stop, seed=run, world="physics", condition=args.condition,
                             kappa=CONDITIONS[args.condition]["kappa"], model=args.model, started_at=started)
                raise SystemExit(f"    {stop}\n    stopped; what was collected is in {partial.relative_to(RESULTS_DIR.parent)}")
            episode.update(model=args.model, model_settings=MODELS[args.model], started_at=started,
                           finished_at=datetime.now(timezone.utc).isoformat())
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(episode, indent=2))
            print(f"    saved {out.relative_to(RESULTS_DIR.parent)}  cost ${episode['cost']:.4f}  "
                  f"report at turn {episode['report_turn']}")


if __name__ == "__main__":
    main()
