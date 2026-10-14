"""Runs inside the sandbox container: loads the runs as `df`, then executes the code read from stdin."""

import sys

import pandas as pd

df = pd.read_csv("/data/runs.csv", keep_default_na=False)
code = sys.stdin.read()
exec(compile(code, "<your code>", "exec"), {"__name__": "__main__", "df": df})
