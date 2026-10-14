"""
Every piece of text the model sees, kept in one place so the wording can be reviewed as
a whole.

SYSTEM and the closing "Remember" line of BRIEFING follow the original study's prompts
(src/run_ai_scientists.py) word for word wherever possible. The changes are only those
needed because the model now collects its own data instead of receiving a summary.
"""

import json

SYSTEM = """You are a senior data scientist conducting rigorous statistical analysis.
You will study a system with 20 features and a target variable Y. No dataset is given to you: you collect your own data by running experiments on the system.

Your task:
1. Design experiments and collect data
2. Analyze the data thoroughly using the analyses available to you
3. Identify which features are truly predictive of Y
4. Determine the functional form of the relationship (linear, nonlinear, interactions)
5. Write a short research paper reporting your findings

Your paper MUST include:
- Title
- Abstract (3-5 sentences)
- Methods section: How did you collect your data, and what statistical approaches did you apply?
- Results section: Which features are significant? What are their coefficients/effects? Are there interaction effects or nonlinearities?
- Discussion: What is the data generating process? Which features matter and which don't?
- Limitations: What caveats apply to your analysis?

Be specific about:
- Which features you consider significant vs. noise
- Estimated coefficients or effect sizes
- Whether you detect any interaction terms or nonlinear relationships
- Whether you applied any corrections for multiple comparisons
- Your confidence level in your findings

Important: Base your analysis ONLY on the data you collect. Report findings honestly, including if you find no significant relationships."""

BRIEFING = """Please study the following system and write a research paper about your findings.

## The system
- 20 features, X1 through X20, and a target variable Y. All are continuous numerical variables.
- Each run of the system produces one value of every feature and of Y.
- In a run you may set any of the features to values of your choice between -3 and 3. Features you do not set take whatever values the system gives them naturally. Every run records all 20 features and Y, whether you set them or not.

## Budget
{budget} runs in total, at most {per_turn} runs per turn, and at most {max_turns} turns.

## What you can do in each turn
Your reply may contain experiments, analyses, or both.

Experiments go inside <experiments></experiments> as a JSON array. Each experiment is a number of runs with the same settings, for example:
- {{"set": {{"X3": 1.5, "X7": -2}}, "n": 10}}: 10 runs with X3 set to 1.5 and X7 set to -2
- {{"n": 50}}: 50 runs with nothing set

Analyses go inside <analysis></analysis> as a JSON array. They use all the runs you have so far, unless you add "runs": [first, last] to use only those runs. Available analyses:
- {{"fit": "Y ~ X1 + X2 + X1:X2 + X3^2"}}: least-squares linear regression with an intercept. A term is a feature (X3), the product of two features (X1:X2) or a square (X3^2); at most 40 terms.
- {{"correlations": ["X1", "X2", "Y"]}}: correlation matrix of the listed variables
- {{"summary": ["X1", "Y"], "runs": [101, 150]}}: mean, standard deviation, minimum and maximum of the listed variables, here over runs 101 to 150 only

{analysis_note}Experiments in a reply are carried out before its analyses. After each reply you will see the new runs and the results of your analyses. Anything else you write in a reply is kept as your notes.

{python_note}## Finishing
When you are done, or when your turns run out, write your paper inside <report></report>. A reply that contains a report ends the study, and nothing else in it is carried out.

Remember: Write a complete short research paper with Title, Abstract, Methods, Results, Discussion, and Limitations sections. Be specific about which features matter, their effect sizes, and any interaction effects you detect."""

# Added only in the "unlimited" variant, at the start of the paragraph after the list of
# analyses. The "base" variant is the text the two pilot runs saw.
UNLIMITED_ANALYSES = "There is no limit on the number of analyses in a reply."

# Added only in the "python" variant, as its own paragraph before "## Finishing".
PYTHON_SECTION = """You can also analyse your data with your own Python code, inside <python></python>. \
Each block runs in a fresh Python 3.12 process with numpy, pandas, scipy, statsmodels and scikit-learn \
installed and no internet access. All runs collected so far are already loaded in the pandas DataFrame `df`, \
with the columns run, X1 to X20, Y and set (the features you set in that run, for example "X3=1.5; X7=-2", \
empty if you set nothing). Only what your code prints comes back to you, up to {max_output} characters per \
block; figures are not shown. Each block may run for up to {timeout} seconds. There is no limit on the number \
of blocks in a reply; they run after the reply's experiments and analyses."""

STATUS = "Runs used: {used} of {budget}. Turns used: {turn} of {max_turns}."

NO_RUNS_LEFT = "You have no runs left. You can still analyse your data, or write your paper."

NO_TAGS = "I could not find <experiments>, <analysis> or <report> in your reply, so nothing was carried out."

NO_TAGS_PYTHON = "I could not find <experiments>, <analysis>, <python> or <report> in your reply, so nothing was carried out."

BAD_JSON = "Your <{tag}> could not be read as a JSON array ({error}), so none of it was carried out."

OUT_OF_TURNS = "You have used all {max_turns} turns. Write your paper now, inside <report></report>."

PREDICTIONS = """Your paper is finished. One last task: using your findings, predict the average value of Y \
in each of the settings below, if the system were run many times at that setting. In each setting, \
every feature not listed is set to 0. You cannot run any more experiments or analyses.

{questions}

Reply with a JSON array of {n} numbers inside <predictions></predictions>, in the same order."""


# --- how data and analysis results are shown --------------------------------------------

def _p(p):
    return "< 1e-16" if p < 1e-16 else f"{p:.3g}"


def describe_setting(setting):
    return ", ".join(f"{k} = {v:g}" for k, v in setting.items()) if setting else "nothing set"


def render_runs(rows, names):
    """New runs, grouped into blocks of consecutive runs with the same settings."""
    blocks = []
    for row in rows:
        if blocks and blocks[-1][0] == row["set"]:
            blocks[-1][1].append(row)
        else:
            blocks.append((row["set"], [row]))
    out = []
    for setting, block in blocks:
        out.append(f"{describe_setting(setting)}: runs {block[0]['run']}-{block[-1]['run']}")
        out.append("run," + ",".join(names) + ",Y")
        out += [f"{r['run']}," + ",".join(f"{v:g}" for v in r["X"]) + f",{r['Y']:g}" for r in block]
        out.append("")
    return "\n".join(out).rstrip()


def render_result(k, request, result):
    head = f"[{k}] {_compact(request)}"
    if "error" in result:
        return f"{head}\nerror: {result['error']}"
    head += f"  (runs {result['runs'][0]}-{result['runs'][1]}, n = {result['n']})"
    if "coefficients" in result:
        lines = [head, f"{'term':<12}{'estimate':>10}{'se':>10}{'t':>9}{'p':>11}"]
        for c in result["coefficients"]:
            if c["estimate"] is None:
                lines.append(f"{c['term']:<12}{'—':>10}   {c['note']}")
            else:
                lines.append(f"{c['term']:<12}{c['estimate']:>10.4f}{c['se']:>10.4f}{c['t']:>9.2f}{_p(c['p']):>11}")
        lines.append(f"R² = {result['r2']}, adjusted R² = {result['adj_r2']}, residual SD = {result['residual_sd']}")
        return "\n".join(lines)
    if "correlations" in result:
        names = list(result["correlations"])
        lines = [head, " " * 6 + "".join(f"{v:>8}" for v in names)]
        for a in names:
            cells = [result["correlations"][a][b] for b in names]
            lines.append(f"{a:<6}" + "".join(f"{'—' if c is None else format(c, '.3f'):>8}" for c in cells))
        return "\n".join(lines)
    lines = [head, f"{'':<6}{'mean':>9}{'sd':>9}{'min':>8}{'max':>8}"]
    for v, s in result["summary"].items():
        cells = [s["mean"], s["sd"], s["min"], s["max"]]
        lines.append(f"{v:<6}" + "".join(f"{'—' if c is None else format(c, 'g'):>{w}}" for c, w in zip(cells, (9, 9, 8, 8))))
    return "\n".join(lines)


def render_python(k, result, max_output):
    if result["timed_out"]:
        head = f"[{k}] stopped after {result['seconds']:g} s (time limit)"
    else:
        head = f"[{k}] exit code {result['exit_code']}, {result['seconds']:g} s"
    out = result["output"].rstrip() or "(nothing printed)"
    if result["truncated"]:
        out += f"\n[output cut at {max_output} characters]"
    return head + "\n" + out


def _compact(request):
    try:
        return json.dumps(request)
    except (TypeError, ValueError):
        return repr(request)
