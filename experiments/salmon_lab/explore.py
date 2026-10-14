"""
Put a model in the lab and let it collect its own data.

Each turn the model may run experiments (choosing what to set) and request analyses of
the data it has collected; it then sees the new runs and the results. The episode ends
when it writes its paper or runs out of turns. It then predicts Y for settings it has
not been asked about before, without further experiments.

Dry run by default: no API calls. A scripted stand-in plays the model's part once, so
the whole loop runs and the exact text a model would see is written to
dry_run/transcript.md. Pass --execute to call the API (OPENROUTER_API_KEY in the
environment or in .env at the repository root). Episodes already on disk are skipped.
"""

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

import prompts
import sandbox
from world import NAMES, LabWorld, questions

HERE = Path(__file__).parent
REPO_ROOT = HERE.parents[1]
RESULTS_DIR = HERE / "results"
DRY_RUN_DIR = HERE / "dry_run"
URL = "https://openrouter.ai/api/v1/chat/completions"

# gpt-4.1 keeps the original study's temperature, with a cap of 8000 tokens instead of 4096.
# The Claude models think before answering and the thinking counts toward max_tokens (the
# original cap cut off all six of the original study's Gemini papers), so they get a larger
# cap, an explicit thinking effort and their default temperature. Each call resends the whole
# conversation; for the Claude models its end is marked for Anthropic's prompt cache, which
# bills the repeated part at a tenth of the input price and leaves what the model sees unchanged.
MODELS = {
    "gpt-4.1": {"id": "openai/gpt-4.1", "temperature": 0.7, "max_tokens": 8000},
    "claude-sonnet-5.5": {"id": "anthropic/claude-sonnet-5.5", "reasoning": {"effort": "medium"}, "max_tokens": 32000,
                          "cache": True},
    "claude-opus-5.5": {"id": "anthropic/claude-opus-5.5", "reasoning": {"effort": "medium"}, "max_tokens": 32000,
                        "cache": True},
}
BUDGET = 300
PER_TURN = 100
MAX_TURNS = 12
# base: the text the pilot runs saw. unlimited: plus one sentence saying analyses are
# unlimited. python: unlimited plus a paragraph offering a Python sandbox (sandbox.py).
VARIANTS = {
    "base": {"analysis_note": "", "python": False},
    "unlimited": {"analysis_note": prompts.UNLIMITED_ANALYSES + " ", "python": False},
    "python": {"analysis_note": prompts.UNLIMITED_ANALYSES + " ", "python": True},
}


def load_api_key():
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.strip().startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return None


def request_body(model, messages):
    cfg = MODELS[model]
    if cfg.get("cache") and messages:
        *earlier, last = messages
        block = {"type": "text", "text": last["content"], "cache_control": {"type": "ephemeral"}}
        messages = [*earlier, {**last, "content": [block]}]
    body = {"model": cfg["id"], "messages": messages, "max_tokens": cfg["max_tokens"], "usage": {"include": True}}
    for option in ("temperature", "reasoning"):
        if option in cfg:
            body[option] = cfg[option]
    return body


class Stopped(Exception):
    """A model call failed partway through an episode; state holds what was collected up to then."""

    def __init__(self, error, state):
        super().__init__(error)
        self.state = state


def total_cost(calls):
    return sum((c["usage"] or {}).get("cost") or 0.0 for c in calls)


def save_partial(path, stop, **info):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**info, "error": str(stop), "cost": total_cost(stop.state["calls"]), **stop.state}, indent=2))


def call(client, key, model, messages):
    for attempt in range(3):
        try:
            resp = client.post(
                URL,
                headers={"Authorization": f"Bearer {key}"},
                json=request_body(model, messages),
                timeout=600,
            )
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            return {
                "content": choice["message"].get("content") or "",
                "reasoning": choice["message"].get("reasoning"),
                "finish_reason": choice.get("finish_reason"),
                "returned_model": data.get("model"),
                "usage": data.get("usage"),
            }
        except (httpx.HTTPStatusError, httpx.TransportError) as err:
            if attempt == 2:
                raise
            print(f"    {err}; retrying")
            time.sleep(10 * (attempt + 1))


def extract(tag, text):
    m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.S)
    return m.group(1).strip() if m else None


def parse_json_array(raw):
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    value = json.loads(raw)
    if not isinstance(value, list):
        raise ValueError("expected a JSON array")
    return value


def opening_messages(variant="base"):
    v = VARIANTS[variant]
    python_note = (prompts.PYTHON_SECTION.format(max_output=sandbox.MAX_OUTPUT, timeout=sandbox.TIMEOUT) + "\n\n"
                   if v["python"] else "")
    briefing = prompts.BRIEFING.format(budget=BUDGET, per_turn=PER_TURN, max_turns=MAX_TURNS,
                                       analysis_note=v["analysis_note"], python_note=python_note)
    return [{"role": "system", "content": prompts.SYSTEM}, {"role": "user", "content": briefing}]


def strip_fences(code):
    """The code without the Markdown fence a model may put around it."""
    return re.sub(r"^\s*```(?:python)?[^\n]*\n|\n?\s*```\s*$", "", code).strip("\n")


def python_blocks(text):
    return [strip_fences(b) for b in re.findall(r"<python>(.*?)</python>", text, re.S)]


def carry_out(world, text, turn, run_code=None):
    """Run a reply's experiments, then its analyses, then (python variant) its code.
    Returns (feedback for the model, record)."""
    record = {"turn": turn}
    raw_exp, raw_ana = extract("experiments", text), extract("analysis", text)
    blocks = python_blocks(text) if run_code else []
    if raw_exp is None and raw_ana is None and not blocks:
        record["error"] = "no tags"
        parts = [prompts.NO_TAGS_PYTHON if run_code else prompts.NO_TAGS]
    else:
        parts = []
        if raw_exp is not None:
            try:
                specs = parse_json_array(raw_exp)
            except (ValueError, json.JSONDecodeError) as err:
                parts.append(prompts.BAD_JSON.format(tag="experiments", error=err))
                record["experiments_error"] = str(err)
            else:
                rows, messages = world.run_experiments(specs)
                record.update(experiments=specs, new_runs=len(rows), refused=messages)
                if rows:
                    parts.append("<runs>\n" + prompts.render_runs(rows, NAMES) + "\n</runs>")
                parts += messages
        if raw_ana is not None:
            try:
                requests = parse_json_array(raw_ana)
            except (ValueError, json.JSONDecodeError) as err:
                parts.append(prompts.BAD_JSON.format(tag="analysis", error=err))
                record["analysis_error"] = str(err)
            else:
                results = world.analyse(requests)
                record.update(analyses=requests, results=results)
                rendered = [prompts.render_result(k, q, r) for k, (q, r) in enumerate(zip(requests, results), 1)]
                parts.append("<analysis_results>\n" + "\n\n".join(rendered) + "\n</analysis_results>")
        if blocks:
            ran = [{"code": code, **run_code(code, *world.code_table())} for code in blocks]
            record["python"] = ran
            rendered = [prompts.render_python(k, r, sandbox.MAX_OUTPUT) for k, r in enumerate(ran, 1)]
            parts.append("<python_output>\n" + "\n\n".join(rendered) + "\n</python_output>")
    record["runs_so_far"] = len(world.rows)
    if world.runs_left() == 0:
        parts.append(prompts.NO_RUNS_LEFT)
    parts.append(prompts.STATUS.format(used=len(world.rows), budget=BUDGET, turn=turn, max_turns=MAX_TURNS))
    return "\n\n".join(parts), record


def run_episode(seed, respond, variant="base", run_code=None):
    """respond(messages) -> {"content", "finish_reason", "returned_model", "usage"}.
    run_code(code, columns, rows) runs a Python block; defaults to the Docker sandbox in the python variant."""
    if not VARIANTS[variant]["python"]:
        run_code = None
    elif run_code is None:
        run_code = sandbox.run_code
    lab = LabWorld(seed, run_budget=BUDGET, max_runs_per_turn=PER_TURN)
    messages = opening_messages(variant)
    calls, turns = [], []
    report, report_turn = None, None

    def ask():
        try:
            r = respond(messages)
        except Exception as err:
            state = {"turns": turns, "rows": lab.rows, "analysis_log": lab.analysis_log, "calls": calls, "messages": messages}
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
            feedback += "\n\n" + prompts.OUT_OF_TURNS.format(max_turns=MAX_TURNS)
        turns.append(record)
        messages.append({"role": "user", "content": feedback})
        print(f"    turn {turn}: {record.get('new_runs', 0)} new runs, {len(record.get('analyses', []))} analyses"
              f"{', ' + str(len(record['python'])) + ' code blocks' if 'python' in record else ''}"
              f"{' (' + record['error'] + ')' if 'error' in record else ''}")

    report_without_tags = False
    if report is None:
        text = ask()
        report = extract("report", text)
        if report is None:
            report, report_without_tags = text, True

    qs = questions()
    listing = "\n".join(f"{i}. {q['text']}" for i, q in enumerate(qs, 1))
    messages.append({"role": "user", "content": prompts.PREDICTIONS.format(questions=listing, n=len(qs))})
    raw_predictions = extract("predictions", ask())
    try:
        predictions = parse_json_array(raw_predictions) if raw_predictions else None
    except (ValueError, json.JSONDecodeError):
        predictions = None

    return {
        "seed": seed,
        "prompt_variant": variant,
        "budget": BUDGET,
        "per_turn": PER_TURN,
        "max_turns": MAX_TURNS,
        "report": report,
        "report_turn": report_turn,
        "report_without_tags": report_without_tags,
        "questions": qs,
        "predictions_raw": raw_predictions,
        "predictions": predictions,
        "turns": turns,
        "rows": lab.rows,
        "analysis_log": lab.analysis_log,
        "calls": calls,
        "cost": total_cost(calls),
        "messages": messages,
    }


# --- dry run --------------------------------------------------------------------------

SCRIPTED_REPLIES = [
    # A stand-in that exercises every part of the protocol. It is not a model.
    'I will start by observing the system without intervening.\n'
    '<experiments>[{"n": 100}]</experiments>\n'
    '<analysis>[{"fit": "Y ~ X1 + X2 + X3 + X4 + X5"}, {"correlations": ["X1", "X16", "Y"]}]</analysis>',
    'Now vary X4 with X5 held at 0.\n'
    '<experiments>[{"set": {"X4": -2, "X5": 0}, "n": 25}, {"set": {"X4": 2, "X5": 0}, "n": 25}, {"n": 5000}]</experiments>\n'
    '<analysis>[{"summary": ["X4", "Y"], "runs": [101, 125]}, {"summary": ["X4", "Y"], "runs": [126, 150]}]</analysis>',
    '<analysis>[{"fit": "Y ~ X4 + X5 + X4:X5", "runs": [101, 150]}, {"fit": "Y ~ X4 + bogus"}]</analysis>',
    'Thinking about what to do next.',
    '<report>Title: (scripted stand-in, not a model)\n\nAbstract: ...</report>',
    '<predictions>[0, 2, -3, 2.5, 0, 0, 0, 0, 2, 0, 0]</predictions>',
]


SCRIPTED_REPLIES_PYTHON = [
    # The same kind of stand-in for the python variant: code that works, code that fails.
    '<experiments>[{"n": 100}]</experiments>\n'
    '<python>\n```python\nimport statsmodels.formula.api as smf\n'
    'print(df.shape)\nprint(smf.ols("Y ~ X1 + X2 + X3", data=df).fit().params.round(2))\n```\n</python>',
    '<experiments>[{"set": {"X4": 2}, "n": 20}]</experiments>\n'
    '<python>print(df.groupby("set")["Y"].agg(["count", "mean"]).round(2))</python>\n'
    '<python>print(df["not_a_column"])</python>',
    'Nothing to run this turn.',
    '<report>Title: (scripted stand-in, not a model)\n\nAbstract: ...</report>',
    '<predictions>[0, 2, -3, 2.5, 0, 0, 0, 0, 2, 0, 0]</predictions>',
]


def scripted(replies):
    it = iter(replies)
    return lambda messages: {"content": next(it), "finish_reason": "stop", "returned_model": "scripted", "usage": None}


def write_transcript(episode, path):
    lines = ["# Dry-run transcript", "",
             "Everything below is exactly what a model would be sent. The assistant turns are a scripted",
             "stand-in that exercises each part of the protocol; they are not a model's replies.", ""]
    for m in episode["messages"]:
        lines += [f"## {m['role']}", "", "```text", m["content"], "```", ""]
    path.write_text("\n".join(lines))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--execute", action="store_true", help="make real API calls")
    p.add_argument("--model", default="gpt-4.1", choices=list(MODELS))
    p.add_argument("--runs", type=int, default=1)
    p.add_argument("--variant", default="base", choices=list(VARIANTS))
    args = p.parse_args()

    if not args.execute:
        replies = SCRIPTED_REPLIES_PYTHON if VARIANTS[args.variant]["python"] else SCRIPTED_REPLIES
        episode = run_episode(seed=0, respond=scripted(replies), variant=args.variant)
        DRY_RUN_DIR.mkdir(exist_ok=True)
        (DRY_RUN_DIR / "episode.json").write_text(json.dumps(episode, indent=2))
        write_transcript(episode, DRY_RUN_DIR / "transcript.md")
        print(f"DRY RUN: no API calls. Transcript written to {(DRY_RUN_DIR / 'transcript.md').relative_to(HERE)}.")
        print(f"Would run {args.runs} episode(s) with {args.model}, {args.variant} prompt. Re-run with --execute.")
        return

    if VARIANTS[args.variant]["python"] and not sandbox.available():
        raise SystemExit("The python variant needs Docker running and the sandbox image built (see sandbox.py).")
    key = load_api_key()
    if not key:
        raise SystemExit("OPENROUTER_API_KEY not found in the environment or in .env at the repo root.")
    with httpx.Client() as client:
        for run in range(1, args.runs + 1):
            out = RESULTS_DIR / args.variant / args.model / f"run{run}.json"
            if out.exists():
                print(f"{out.relative_to(HERE)} exists, skipping")
                continue
            print(f"{args.variant} / {args.model} / run {run}")
            started = datetime.now(timezone.utc).isoformat()
            try:
                episode = run_episode(run, lambda messages: call(client, key, args.model, messages), args.variant)
            except Stopped as stop:
                partial = out.with_name(f"run{run}.partial.json")
                save_partial(partial, stop, seed=run, prompt_variant=args.variant, model=args.model, started_at=started)
                raise SystemExit(f"    {stop}\n    stopped; what was collected is in {partial.relative_to(HERE)}")
            episode.update(model=args.model, model_settings=MODELS[args.model], started_at=started,
                           finished_at=datetime.now(timezone.utc).isoformat())
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(episode, indent=2))
            print(f"    saved {out.relative_to(HERE)}  cost ${episode['cost']:.4f}  "
                  f"report at turn {episode['report_turn']}")


if __name__ == "__main__":
    main()
