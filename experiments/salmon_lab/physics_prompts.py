"""
Every piece of text the model sees in the physics lab. The structure follows prompts.py:
the paper sections and the "be specific" list mirror those of the statistical world.
"""

SYSTEM = """You are a scientist studying how objects move in a simulated physics laboratory. The laws of physics in this laboratory may differ from those of the real world. No dataset is given to you: you collect your own data by running experiments, and you analyse it with your own code.

Your task:
1. Design experiments and collect data
2. Analyze the data thoroughly
3. Identify which properties of an object and which launch settings affect its motion
4. Determine the form of each effect, including whether any effect depends on a combination of properties
5. Write a short research paper reporting your findings
6. Submit your law as a Python function that predicts the outcome of an experiment

Your paper MUST include:
- Title
- Abstract (3-5 sentences)
- Methods section: How did you collect your data, and how did you analyze it?
- Results section: What affects the motion, in what way, and how strongly?
- Discussion: What laws govern this laboratory? Which properties matter and which don't?
- Limitations: What caveats apply to your analysis?

Be specific about:
- Which properties and settings you consider to have an effect, and which you consider irrelevant
- The form and size of each effect
- Whether any effect depends on a combination of properties
- Your confidence level in your findings

Important: Base your conclusions ONLY on the data you collect. Report findings honestly, including if you find no effect."""

BRIEFING = """Please study the following laboratory and write a research paper about your findings.

## The laboratory
In each run an object is released or thrown. The laboratory measures how long it takes to reach the ground (flight_time, in s), how far it travels horizontally before landing (distance, in m) and its speed when it lands (impact_speed, in m/s). {measurement_error}

Object properties:
- mass: 0.1 to 10 kg
- radius: 0.02 to 0.2 m
- shape: sphere, cube or cylinder
- reflectance: 0 (black) to 1 (white)
- temperature: -20 to 80 °C
- stripes: 0 to 10 (number of painted stripes)
- hardness: 1 to 10
- batch: 1 to 50 (production batch)

Launch settings:
- height: 0.5 to 50 m (default 10)
- speed: 0 to 20 m/s (default 0)
- angle: -90 to 90 degrees, where 0 is horizontal and 90 is straight up (default 0)
- air_density: 0 (vacuum) to 2.4 kg/m^3 (default 1.2)

In a run you may set any object properties and any launch settings. Object properties you do not set are those of an object taken at random from the laboratory's stock; launch settings you do not set take their default values. Every run records all properties, all settings and the three measurements.

## Budget
{budget} runs in total, at most {per_turn} runs per turn, and at most {max_turns} turns.

## What you can do in each turn
Your reply may contain experiments, Python code, or both.

Experiments go inside <experiments></experiments> as a JSON array. Each experiment is a number of runs with the same settings, for example:
- {{"object": {{"mass": 2, "shape": "cube"}}, "launch": {{"height": 30, "air_density": 0}}, "n": 10}}: 10 runs dropping a 2 kg cube from 30 m in a vacuum, its other properties random
- {{"n": 50}}: 50 runs with random objects and the default launch settings

You analyse your data with your own Python code, inside <python></python>. Each block runs in a fresh Python 3.12 process with numpy, pandas, scipy, statsmodels and scikit-learn installed and no internet access. All runs collected so far are already loaded in the pandas DataFrame `df`, with one column for each property, setting and measurement, plus run and set (what you set in that run, for example "temperature=70; height=30", empty if you set nothing). Only what your code prints comes back to you, up to {max_output} characters per block; figures are not shown. Each block may run for up to {timeout} seconds. There is no limit on the number of blocks in a reply.

Experiments in a reply are carried out before its code. After each reply you will see the new runs and the output of your code. Anything else you write in a reply is kept as your notes.

## Finishing
When you are done, or when your turns run out, write your paper inside <report></report>. A reply that contains a report ends the study, and nothing else in it is carried out. You will then be asked for your law.

Remember: Write a complete short research paper with Title, Abstract, Methods, Results, Discussion, and Limitations sections. Be specific about which properties and settings matter, the form and size of their effects, and any effect that depends on a combination of properties."""

ERROR_UNSTATED = "Measurements include a small random error."

ERROR_STATED = ("Measurements include a small random error, independent for every measurement, with a standard "
                "deviation of {time:g} s for flight_time and {relative:.0%} of the true value for distance and impact_speed.")

STATUS = "Runs used: {used} of {budget}. Turns used: {turn} of {max_turns}."

NO_RUNS_LEFT = "You have no runs left. You can still analyse your data, or write your paper."

NO_TAGS = "I could not find <experiments>, <python> or <report> in your reply, so nothing was carried out."

BAD_JSON = "Your <experiments> could not be read as a JSON array ({error}), so none of it was carried out."

OUT_OF_TURNS = "You have used all {max_turns} turns. Write your paper now, inside <report></report>."

LAW = """Your paper is finished. Now submit your law as a Python function inside <law></law>:

def predict(obj, launch):
    ...
    return {{"flight_time": ..., "distance": ..., "impact_speed": ...}}

obj has the keys mass, radius, shape, reflectance, temperature, stripes, hardness and batch; launch has the keys height, speed, angle and air_density, in the units above. The function may import math, numpy and scipy, must not read any files, and should take well under a second per call. It will be tested on {n} experiments you have not run. You cannot run any more experiments or code."""


def render_runs(rows, columns, describe):
    """New runs, grouped into blocks of consecutive runs with the same settings."""
    blocks = []
    for row in rows:
        if blocks and blocks[-1][0] == row["set"]:
            blocks[-1][1].append(row)
        else:
            blocks.append((row["set"], [row]))
    fmt = lambda v: v if isinstance(v, str) else f"{v:g}"
    out = []
    for setting, block in blocks:
        out.append(f"{describe(setting)}: runs {block[0]['run']}-{block[-1]['run']}")
        out.append(",".join(columns))
        for r in block:
            values = [r["run"], *r["object"].values(), *r["launch"].values(), r["flight_time"], r["distance"], r["impact_speed"]]
            out.append(",".join(fmt(v) for v in values))
        out.append("")
    return "\n".join(out).rstrip()
