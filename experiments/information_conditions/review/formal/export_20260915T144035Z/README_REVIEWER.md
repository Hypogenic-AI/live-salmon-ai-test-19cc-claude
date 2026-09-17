# Reviewer instructions (30 papers)

1. Read RUBRIC.md in experiments/information_conditions/ first.
2. For each `papers/<ID>.md`, fill `forms/<ID>.json`. Use the enumerations in review_schema.json.
3. Score claim strength by what the sentence asserts, not by the section it sits in. Save the supporting quote and section.
4. If a paper contradicts itself about a target, set contradictory_statements=true and record both quotes.
5. You are not told which dataset or condition a paper came from. Do not try to infer it; score the text.
6. When all forms are filled, run `cli.py lock-reviews --export-dir <this dir>` before anyone unmasks.

Optional aid: `aid/<ID>.json` (if present) lists regex hits for interaction terms and keywords. It is only a pointer to passages; it does not score anything.
