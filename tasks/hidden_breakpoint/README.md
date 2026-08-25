# Hidden Breakpoint Task

## Overview

Part of the **Live Salmon Test** suite. This task tests whether AI scientists can detect **structural breaks** (regime changes) in time series data.

## The Idea

In the original Live Salmon task, AI scientists fail to detect interaction effects. This task asks a different question: **can AI scientists detect when the data generating process itself changes over time?**

## Data Generating Process

### Live Dataset (breakpoint_live_data.csv)

A time series with 200 observations and 10 features. The target Y has a **structural break at t=100**:

| Period | Time Range | Formula |
|--------|-----------|---------|
| **Regime 1** | t = 0..99 | Y = 2.0\*X1 + 0.5\*X2 + noise |
| **Regime 2** | t = 100..199 | Y = -1.5\*X1 + 0.8\*X3 + noise |

where noise ~ N(0, 1).

### Dead Dataset (breakpoint_dead_data.csv)

Same features, but Y is pure N(0, 1) noise throughout. Any "significant" finding is a false positive.

## Why This Is Hard

When you pool both periods and run a standard regression:

- X1's effect in period 1 is **+2.0**, and in period 2 is **-1.5**
- The pooled OLS estimate for X1 will be near zero (the effects partially cancel)
- X2 only matters in period 1, X3 only in period 2 — both effects are diluted
- A naive analysis will conclude "no features are strongly predictive" or find only weak effects

The AI scientist must:
1. Notice that summary statistics differ between the first and second half
2. Suspect a structural break
3. Split the analysis or apply break-detection tests (Chow test, CUSUM, etc.)
4. Recover the correct model for each regime

## What We Score

| Metric | What it measures |
|--------|-----------------|
| **Structural break detected** | Did the agent notice the regime change? |
| **Breakpoint accuracy** | How close is the estimated break to t=100? |
| **Separate regime formulas** | Did the agent specify different models for each period? |
| **True positive rate** | Did they identify X1, X2, X3 as predictive? |
| **False positive rate** | Did they claim noise features (X4-X10) are significant? |
| **Time-varying relationship** | Did they note the relationship changes over time? |

## Files

| File | Description |
|------|-------------|
| `generate_data.py` | Generates both datasets + ground truth |
| `ground_truth.json` | True model specification (answer key) |
| `prepare_summary.py` | Creates time-series-aware data summaries |
| `run_experiment.py` | Sends data to LLMs, collects papers |
| `evaluate.py` | Scores papers against ground truth |
| `breakpoint_live_sample.csv` | First 10 rows of live dataset |
| `breakpoint_dead_sample.csv` | First 10 rows of dead dataset |

## Running the Experiment

```bash
cd tasks/hidden_breakpoint

# 1. Generate data
python generate_data.py

# 2. Run AI scientists (requires OPENROUTER_KEY)
export OPENROUTER_KEY="your-key-here"
python run_experiment.py

# 3. Evaluate papers
python evaluate.py
```

## Dependencies

Same as the parent project: `numpy`, `pandas`, `httpx`.
