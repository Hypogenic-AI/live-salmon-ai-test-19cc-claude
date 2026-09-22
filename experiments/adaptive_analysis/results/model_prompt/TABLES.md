# Model × prompt Live Salmon experiment

Status: **complete**. Formal records: 180/180. Development records: 36/36. Missing configurations remain visible in every table and metrics.json.

The planned factorial comparison uses three model profiles, P0/P1 instructions, fixed/adaptive workflows, global/conditional/null data, and formal seeds 301–305. Development seed 9010 is separate. Exact frozen prompts and transport settings are retained in freeze and metrics.json. Do not pool this experiment with the earlier GPT-4.1 pilot.

Each episode uses 1,000 rows, 700 discovery rows, 300 hidden test rows, and five-fold discovery CV. The conditional term is sqrt(2) × 0.8 × X4 × X5 × I(X6 > 0), with seed-specific anonymization. A uses exhaustive fixed evidence followed by one model selection; B adaptively selects analysis tools with up to eight analysis actions. Shared tools do not imply equal evidence volume, model calls, or computation. These compare workflows, not an isolated causal effect of feedback.

## Model identity

| Profile | Requested models | Observed actual models | Actual-model coverage |
| --- | --- | --- | --- |
| gpt4.1 | openai/gpt-4.1 | openai/gpt-4.1 | 171/173 calls |
| sol_medium | openai/gpt-5.6-sol | openai/gpt-5.6-sol | 165/166 calls |
| astra_medium | openai/gpt-6-astra | openai/gpt-6-astra | 213/215 calls |

Returned model names are provider metadata, not proof of a particular immutable backend revision. Missing actual-model, finish-reason, reasoning-token, and billing fields remain unknown. Requested reasoning effort is a configuration, while reported reasoning tokens describe usage when available.

## Formal outcomes

| Profile | Prompt | Data | Workflow | Completed / planned | Exact structure / planned | Test MSE (n) | False condition (n) | False signal (n) | Failed / nonterminal / missing |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gpt4.1 | P0 | global | fixed | 5/5 | 1/5 | 1.01891 (n=5) | 0.80000 (n=5) | NA (n=0) | 0/0/0 |
| gpt4.1 | P0 | global | adaptive | 5/5 | 5/5 | 1.01046 (n=5) | 0.00000 (n=5) | NA (n=0) | 0/0/0 |
| gpt4.1 | P0 | conditional | fixed | 5/5 | 5/5 | 1.01927 (n=5) | NA (n=0) | NA (n=0) | 0/0/0 |
| gpt4.1 | P0 | conditional | adaptive | 5/5 | 0/5 | 1.34016 (n=5) | NA (n=0) | NA (n=0) | 0/0/0 |
| gpt4.1 | P0 | null | fixed | 5/5 | 0/5 | 1.03413 (n=5) | 1.00000 (n=5) | 1.00000 (n=5) | 0/0/0 |
| gpt4.1 | P0 | null | adaptive | 4/5 | 0/5 | 1.01192 (n=4) | 0.00000 (n=4) | 1.00000 (n=4) | 1/0/0 |
| gpt4.1 | P1 | global | fixed | 5/5 | 2/5 | 1.02110 (n=5) | 0.60000 (n=5) | NA (n=0) | 0/0/0 |
| gpt4.1 | P1 | global | adaptive | 5/5 | 5/5 | 1.01046 (n=5) | 0.00000 (n=5) | NA (n=0) | 0/0/0 |
| gpt4.1 | P1 | conditional | fixed | 5/5 | 5/5 | 1.01927 (n=5) | NA (n=0) | NA (n=0) | 0/0/0 |
| gpt4.1 | P1 | conditional | adaptive | 5/5 | 0/5 | 1.34016 (n=5) | NA (n=0) | NA (n=0) | 0/0/0 |
| gpt4.1 | P1 | null | fixed | 4/5 | 0/5 | 1.05850 (n=4) | 1.00000 (n=4) | 1.00000 (n=4) | 1/0/0 |
| gpt4.1 | P1 | null | adaptive | 5/5 | 3/5 | 0.99140 (n=5) | 0.00000 (n=5) | 0.40000 (n=5) | 0/0/0 |
| sol_medium | P0 | global | fixed | 5/5 | 4/5 | 1.00827 (n=5) | 0.20000 (n=5) | NA (n=0) | 0/0/0 |
| sol_medium | P0 | global | adaptive | 0/5 | 0/5 | NA (n=0) | NA (n=0) | NA (n=0) | 5/0/0 |
| sol_medium | P0 | conditional | fixed | 5/5 | 5/5 | 1.01927 (n=5) | NA (n=0) | NA (n=0) | 0/0/0 |
| sol_medium | P0 | conditional | adaptive | 0/5 | 0/5 | NA (n=0) | NA (n=0) | NA (n=0) | 5/0/0 |
| sol_medium | P0 | null | fixed | 5/5 | 5/5 | 0.98439 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 0/0/0 |
| sol_medium | P0 | null | adaptive | 1/5 | 1/5 | 1.01197 (n=1) | 0.00000 (n=1) | 0.00000 (n=1) | 4/0/0 |
| sol_medium | P1 | global | fixed | 5/5 | 5/5 | 1.01046 (n=5) | 0.00000 (n=5) | NA (n=0) | 0/0/0 |
| sol_medium | P1 | global | adaptive | 5/5 | 5/5 | 1.01046 (n=5) | 0.00000 (n=5) | NA (n=0) | 0/0/0 |
| sol_medium | P1 | conditional | fixed | 5/5 | 5/5 | 1.01927 (n=5) | NA (n=0) | NA (n=0) | 0/0/0 |
| sol_medium | P1 | conditional | adaptive | 0/5 | 0/5 | NA (n=0) | NA (n=0) | NA (n=0) | 5/0/0 |
| sol_medium | P1 | null | fixed | 5/5 | 5/5 | 0.98439 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 0/0/0 |
| sol_medium | P1 | null | adaptive | 4/5 | 4/5 | 0.97917 (n=4) | 0.00000 (n=4) | 0.00000 (n=4) | 1/0/0 |
| astra_medium | P0 | global | fixed | 5/5 | 5/5 | 1.01046 (n=5) | 0.00000 (n=5) | NA (n=0) | 0/0/0 |
| astra_medium | P0 | global | adaptive | 5/5 | 5/5 | 1.01046 (n=5) | 0.00000 (n=5) | NA (n=0) | 0/0/0 |
| astra_medium | P0 | conditional | fixed | 5/5 | 5/5 | 1.01927 (n=5) | NA (n=0) | NA (n=0) | 0/0/0 |
| astra_medium | P0 | conditional | adaptive | 5/5 | 5/5 | 1.01927 (n=5) | NA (n=0) | NA (n=0) | 0/0/0 |
| astra_medium | P0 | null | fixed | 5/5 | 5/5 | 0.98439 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 0/0/0 |
| astra_medium | P0 | null | adaptive | 5/5 | 5/5 | 0.98439 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 0/0/0 |
| astra_medium | P1 | global | fixed | 5/5 | 5/5 | 1.01046 (n=5) | 0.00000 (n=5) | NA (n=0) | 0/0/0 |
| astra_medium | P1 | global | adaptive | 5/5 | 5/5 | 1.01046 (n=5) | 0.00000 (n=5) | NA (n=0) | 0/0/0 |
| astra_medium | P1 | conditional | fixed | 5/5 | 5/5 | 1.01927 (n=5) | NA (n=0) | NA (n=0) | 0/0/0 |
| astra_medium | P1 | conditional | adaptive | 3/5 | 3/5 | 1.01702 (n=3) | NA (n=0) | NA (n=0) | 2/0/0 |
| astra_medium | P1 | null | fixed | 5/5 | 5/5 | 0.98439 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 0/0/0 |
| astra_medium | P1 | null | adaptive | 5/5 | 5/5 | 0.98439 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 0/0/0 |

Exact-structure success includes the existing direction check; it does not establish causality or recover all main-effect coefficients. Planned denominators include failures; missing records make this report provisional. MSE and false-selection means use successful applicable episodes only, with explicit n. False condition applies to global/null, false signal to null. These are model-selection frequencies, not calibrated statistical test error rates. Five seeds per cell support descriptive comparison, not a general ranking of models or significance claims.

## Formal resources

| Profile | Prompt | Data | Workflow | Mean fits (n) | Mean calls (n) | USD / coverage | Tokens / episode coverage | Reasoning tokens / known coverage | Mean seconds (n) | Failed attempts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gpt4.1 | P0 | global | fixed | 21672.00000 (n=5) | 1.00000 (n=5) | 0.107020; 5/5 episodes, 5/5 calls | 51527 (5/5) | 0 (5/5 calls; 5/5 complete episodes) | 18.66692 (n=5) | 0 |
| gpt4.1 | P0 | global | adaptive | 1146.00000 (n=5) | 3.00000 (n=5) | 0.203434; 5/5 episodes, 15/15 calls | 99425 (5/5) | 0 (15/15 calls; 5/5 complete episodes) | 4.71688 (n=5) | 0 |
| gpt4.1 | P0 | conditional | fixed | 21672.00000 (n=5) | 1.00000 (n=5) | 0.107692; 5/5 episodes, 5/5 calls | 51596 (5/5) | 0 (5/5 calls; 5/5 complete episodes) | 19.44843 (n=5) | 0 |
| gpt4.1 | P0 | conditional | adaptive | 1146.00000 (n=5) | 3.60000 (n=5) | 0.252286; 5/5 episodes, 18/18 calls | 123578 (5/5) | 0 (18/18 calls; 5/5 complete episodes) | 5.47364 (n=5) | 0 |
| gpt4.1 | P0 | null | fixed | 21672.00000 (n=5) | 1.00000 (n=5) | 0.107502; 5/5 episodes, 5/5 calls | 51657 (5/5) | 0 (5/5 calls; 5/5 complete episodes) | 19.15478 (n=5) | 0 |
| gpt4.1 | P0 | null | adaptive | 920.40000 (n=5) | 3.60000 (n=5) | >=0.232240 known; 4/5 episodes, 17/18 calls | 108312 (4/5) | >=0 known (17/18 calls; 4/5 complete episodes) | 28.77036 (n=5) | 1 |
| gpt4.1 | P1 | global | fixed | 21672.00000 (n=5) | 1.00000 (n=5) | 0.114346; 5/5 episodes, 5/5 calls | 53369 (5/5) | 0 (5/5 calls; 5/5 complete episodes) | 20.17179 (n=5) | 0 |
| gpt4.1 | P1 | global | adaptive | 1152.00000 (n=5) | 4.20000 (n=5) | 0.295216; 5/5 episodes, 21/21 calls | 142967 (5/5) | 0 (21/21 calls; 5/5 complete episodes) | 7.97819 (n=5) | 0 |
| gpt4.1 | P1 | conditional | fixed | 21672.00000 (n=5) | 1.00000 (n=5) | 0.113938; 5/5 episodes, 5/5 calls | 53303 (5/5) | 0 (5/5 calls; 5/5 complete episodes) | 21.10395 (n=5) | 0 |
| gpt4.1 | P1 | conditional | adaptive | 1152.00000 (n=5) | 4.00000 (n=5) | 0.281290; 5/5 episodes, 20/20 calls | 136022 (5/5) | 0 (20/20 calls; 5/5 complete episodes) | 6.15249 (n=5) | 0 |
| gpt4.1 | P1 | null | fixed | 21672.00000 (n=5) | 1.00000 (n=5) | >=0.092370 known; 4/5 episodes, 4/5 calls | 42867 (4/5) | >=0 known (4/5 calls; 4/5 complete episodes) | 44.09766 (n=5) | 1 |
| gpt4.1 | P1 | null | adaptive | 1152.00000 (n=5) | 4.00000 (n=5) | 0.280514; 5/5 episodes, 20/20 calls | 135997 (5/5) | 0 (20/20 calls; 5/5 complete episodes) | 6.34869 (n=5) | 0 |
| sol_medium | P0 | global | fixed | 21672.00000 (n=5) | 1.00000 (n=5) | 0.140055; 5/5 episodes, 5/5 calls | 52152 (5/5) | 615 (5/5 calls; 5/5 complete episodes) | 23.04104 (n=5) | 0 |
| sol_medium | P0 | global | adaptive | 6.00000 (n=5) | 2.00000 (n=5) | 0.155963; 5/5 episodes, 10/10 calls | 60114 (5/5) | 344 (10/10 calls; 5/5 complete episodes) | 5.08586 (n=5) | 5 |
| sol_medium | P0 | conditional | fixed | 21672.00000 (n=5) | 1.00000 (n=5) | 0.137435; 5/5 episodes, 5/5 calls | 51875 (5/5) | 285 (5/5 calls; 5/5 complete episodes) | 20.97665 (n=5) | 0 |
| sol_medium | P0 | conditional | adaptive | 3.60000 (n=5) | 1.60000 (n=5) | 0.123138; 5/5 episodes, 8/8 calls | 47601 (5/5) | 260 (8/8 calls; 5/5 complete episodes) | 3.90272 (n=5) | 5 |
| sol_medium | P0 | null | fixed | 21672.00000 (n=5) | 1.00000 (n=5) | 0.135688; 5/5 episodes, 5/5 calls | 51785 (5/5) | 316 (5/5 calls; 5/5 complete episodes) | 21.08979 (n=5) | 0 |
| sol_medium | P0 | null | adaptive | 460.80000 (n=5) | 2.20000 (n=5) | 0.184311; 5/5 episodes, 11/11 calls | 70707 (5/5) | 600 (11/11 calls; 5/5 complete episodes) | 6.78203 (n=5) | 4 |
| sol_medium | P1 | global | fixed | 21672.00000 (n=5) | 1.00000 (n=5) | 0.150083; 5/5 episodes, 5/5 calls | 54081 (5/5) | 661 (5/5 calls; 5/5 complete episodes) | 23.43026 (n=5) | 0 |
| sol_medium | P1 | global | adaptive | 1260.00000 (n=5) | 5.00000 (n=5) | 0.504565; 5/5 episodes, 25/25 calls | 191128 (5/5) | 1515 (25/25 calls; 5/5 complete episodes) | 18.48368 (n=5) | 0 |
| sol_medium | P1 | conditional | fixed | 21672.00000 (n=5) | 1.00000 (n=5) | 0.149643; 5/5 episodes, 5/5 calls | 54022 (5/5) | 612 (5/5 calls; 5/5 complete episodes) | 22.64875 (n=5) | 0 |
| sol_medium | P1 | conditional | adaptive | 1326.00000 (n=5) | 5.80000 (n=5) | 0.630926; 5/5 episodes, 29/29 calls | 242953 (5/5) | 1802 (29/29 calls; 5/5 complete episodes) | 18.21570 (n=5) | 5 |
| sol_medium | P1 | null | fixed | 21672.00000 (n=5) | 1.00000 (n=5) | 0.143955; 5/5 episodes, 5/5 calls | 53538 (5/5) | 279 (5/5 calls; 5/5 complete episodes) | 21.33316 (n=5) | 0 |
| sol_medium | P1 | null | adaptive | 1238.40000 (n=5) | 4.80000 (n=5) | 0.471017; 5/5 episodes, 24/24 calls | 179931 (5/5) | 1240 (24/24 calls; 5/5 complete episodes) | 15.24620 (n=5) | 1 |
| astra_medium | P0 | global | fixed | 21672.00000 (n=5) | 1.00000 (n=5) | 0.678825; 5/5 episodes, 5/5 calls | 51723 (5/5) | 0 (5/5 calls; 5/5 complete episodes) | 22.39999 (n=5) | 0 |
| astra_medium | P0 | global | adaptive | 1254.00000 (n=5) | 4.00000 (n=5) | 1.953688; 5/5 episodes, 20/20 calls | 151393 (5/5) | 184 (20/20 calls; 5/5 complete episodes) | 13.40969 (n=5) | 0 |
| astra_medium | P0 | conditional | fixed | 21672.00000 (n=5) | 1.00000 (n=5) | 0.689225; 5/5 episodes, 5/5 calls | 51916 (5/5) | 0 (5/5 calls; 5/5 complete episodes) | 22.46606 (n=5) | 0 |
| astra_medium | P0 | conditional | adaptive | 1256.40000 (n=5) | 4.40000 (n=5) | 2.231835; 5/5 episodes, 22/22 calls | 172668 (5/5) | 346 (22/22 calls; 5/5 complete episodes) | 16.13827 (n=5) | 0 |
| astra_medium | P0 | null | fixed | 21672.00000 (n=5) | 1.00000 (n=5) | 0.679388; 5/5 episodes, 5/5 calls | 51804 (5/5) | 0 (5/5 calls; 5/5 complete episodes) | 22.49105 (n=5) | 0 |
| astra_medium | P0 | null | adaptive | 1216.80000 (n=5) | 4.60000 (n=5) | 2.163015; 5/5 episodes, 23/23 calls | 167976 (5/5) | 311 (23/23 calls; 5/5 complete episodes) | 15.90750 (n=5) | 0 |
| astra_medium | P1 | global | fixed | 21672.00000 (n=5) | 1.00000 (n=5) | 0.726313; 5/5 episodes, 5/5 calls | 53599 (5/5) | 0 (5/5 calls; 5/5 complete episodes) | 25.74926 (n=5) | 0 |
| astra_medium | P1 | global | adaptive | 1260.00000 (n=5) | 5.00000 (n=5) | 2.480375; 5/5 episodes, 25/25 calls | 190279 (5/5) | 440 (25/25 calls; 5/5 complete episodes) | 20.36216 (n=5) | 0 |
| astra_medium | P1 | conditional | fixed | 21672.00000 (n=5) | 1.00000 (n=5) | 0.733712; 5/5 episodes, 5/5 calls | 53732 (5/5) | 0 (5/5 calls; 5/5 complete episodes) | 24.98178 (n=5) | 0 |
| astra_medium | P1 | conditional | adaptive | 1270.80000 (n=5) | 6.80000 (n=5) | >=3.428085 known; 3/5 episodes, 32/34 calls | 180448 (3/5) | >=590 known (32/34 calls; 3/5 complete episodes) | 45.50530 (n=5) | 2 |
| astra_medium | P1 | null | fixed | 21672.00000 (n=5) | 1.00000 (n=5) | 0.723925; 5/5 episodes, 5/5 calls | 53621 (5/5) | 0 (5/5 calls; 5/5 complete episodes) | 25.17404 (n=5) | 0 |
| astra_medium | P1 | null | adaptive | 1260.00000 (n=5) | 5.00000 (n=5) | 2.479675; 5/5 episodes, 25/25 calls | 190448 (5/5) | 471 (25/25 calls; 5/5 complete episodes) | 20.93976 (n=5) | 0 |

All retained attempts contribute resource costs. A scan consumes one analysis action but its full internal fits are counted. Missing provider costs are not zero; partial known sums and episode/call coverage are explicit. Interrupted work may have unpersisted time or fits. Reasoning tokens may be a subset of completion tokens and must not be added to total tokens.

## Paired changes

| Contrast (right − left) | Profile | Other factor | Data | Δ structure (n) | Δ MSE (n) | Δ fits (n) | Δ calls (n) | Δ USD (n) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P1_minus_P0 | gpt4.1 | fixed | global | 0.20000 (5) | 0.00219 (5) | 0.00000 (5) | 0.00000 (5) | 0.00147 (5) |
| P1_minus_P0 | gpt4.1 | fixed | conditional | 0.00000 (5) | 0.00000 (5) | 0.00000 (5) | 0.00000 (5) | 0.00125 (5) |
| P1_minus_P0 | gpt4.1 | fixed | null | 0.00000 (5) | 0.00000 (4) | 0.00000 (5) | 0.00000 (5) | 0.00162 (4) |
| P1_minus_P0 | gpt4.1 | adaptive | global | 0.00000 (5) | 0.00000 (5) | 6.00000 (5) | 1.20000 (5) | 0.01836 (5) |
| P1_minus_P0 | gpt4.1 | adaptive | conditional | 0.00000 (5) | 0.00000 (5) | 6.00000 (5) | 0.40000 (5) | 0.00580 (5) |
| P1_minus_P0 | gpt4.1 | adaptive | null | 0.60000 (5) | -0.02973 (4) | 231.60000 (5) | 0.40000 (5) | 0.00083 (4) |
| P1_minus_P0 | sol_medium | fixed | global | 0.20000 (5) | 0.00219 (5) | 0.00000 (5) | 0.00000 (5) | 0.00201 (5) |
| P1_minus_P0 | sol_medium | fixed | conditional | 0.00000 (5) | 0.00000 (5) | 0.00000 (5) | 0.00000 (5) | 0.00244 (5) |
| P1_minus_P0 | sol_medium | fixed | null | 0.00000 (5) | 0.00000 (5) | 0.00000 (5) | 0.00000 (5) | 0.00165 (5) |
| P1_minus_P0 | sol_medium | adaptive | global | 1.00000 (5) | NA (0) | 1254.00000 (5) | 3.00000 (5) | 0.06972 (5) |
| P1_minus_P0 | sol_medium | adaptive | conditional | 0.00000 (5) | NA (0) | 1322.40000 (5) | 4.20000 (5) | 0.10156 (5) |
| P1_minus_P0 | sol_medium | adaptive | null | 0.60000 (5) | 0.00000 (1) | 777.60000 (5) | 2.60000 (5) | 0.05734 (5) |
| P1_minus_P0 | astra_medium | fixed | global | 0.00000 (5) | 0.00000 (5) | 0.00000 (5) | 0.00000 (5) | 0.00950 (5) |
| P1_minus_P0 | astra_medium | fixed | conditional | 0.00000 (5) | 0.00000 (5) | 0.00000 (5) | 0.00000 (5) | 0.00890 (5) |
| P1_minus_P0 | astra_medium | fixed | null | 0.00000 (5) | 0.00000 (5) | 0.00000 (5) | 0.00000 (5) | 0.00891 (5) |
| P1_minus_P0 | astra_medium | adaptive | global | 0.00000 (5) | 0.00000 (5) | 6.00000 (5) | 1.00000 (5) | 0.10534 (5) |
| P1_minus_P0 | astra_medium | adaptive | conditional | -0.40000 (5) | 0.00000 (3) | 14.40000 (5) | 2.40000 (5) | 0.38660 (3) |
| P1_minus_P0 | astra_medium | adaptive | null | 0.00000 (5) | 0.00000 (5) | 43.20000 (5) | 0.40000 (5) | 0.06333 (5) |
| adaptive_minus_fixed | gpt4.1 | P0 | global | 0.80000 (5) | -0.00845 (5) | -20526.00000 (5) | 2.00000 (5) | 0.01928 (5) |
| adaptive_minus_fixed | gpt4.1 | P0 | conditional | -1.00000 (5) | 0.32089 (5) | -20526.00000 (5) | 2.60000 (5) | 0.02892 (5) |
| adaptive_minus_fixed | gpt4.1 | P0 | null | 0.00000 (5) | -0.01767 (4) | -20751.60000 (5) | 2.60000 (5) | 0.03372 (4) |
| adaptive_minus_fixed | gpt4.1 | P1 | global | 0.60000 (5) | -0.01064 (5) | -20520.00000 (5) | 3.20000 (5) | 0.03617 (5) |
| adaptive_minus_fixed | gpt4.1 | P1 | conditional | -1.00000 (5) | 0.32089 (5) | -20520.00000 (5) | 3.00000 (5) | 0.03347 (5) |
| adaptive_minus_fixed | gpt4.1 | P1 | null | 0.60000 (5) | -0.05604 (4) | -20520.00000 (5) | 3.00000 (5) | 0.03293 (4) |
| adaptive_minus_fixed | sol_medium | P0 | global | -0.80000 (5) | NA (0) | -21666.00000 (5) | 1.00000 (5) | 0.00318 (5) |
| adaptive_minus_fixed | sol_medium | P0 | conditional | -1.00000 (5) | NA (0) | -21668.40000 (5) | 0.60000 (5) | -0.00286 (5) |
| adaptive_minus_fixed | sol_medium | P0 | null | -0.80000 (5) | 0.00000 (1) | -21211.20000 (5) | 1.20000 (5) | 0.00972 (5) |
| adaptive_minus_fixed | sol_medium | P1 | global | 0.00000 (5) | 0.00000 (5) | -20412.00000 (5) | 4.00000 (5) | 0.07090 (5) |
| adaptive_minus_fixed | sol_medium | P1 | conditional | -1.00000 (5) | NA (0) | -20346.00000 (5) | 4.80000 (5) | 0.09626 (5) |
| adaptive_minus_fixed | sol_medium | P1 | null | -0.20000 (5) | 0.00000 (4) | -20433.60000 (5) | 3.80000 (5) | 0.06541 (5) |
| adaptive_minus_fixed | astra_medium | P0 | global | 0.00000 (5) | 0.00000 (5) | -20418.00000 (5) | 3.00000 (5) | 0.25497 (5) |
| adaptive_minus_fixed | astra_medium | P0 | conditional | 0.00000 (5) | 0.00000 (5) | -20415.60000 (5) | 3.40000 (5) | 0.30852 (5) |
| adaptive_minus_fixed | astra_medium | P0 | null | 0.00000 (5) | 0.00000 (5) | -20455.20000 (5) | 3.60000 (5) | 0.29673 (5) |
| adaptive_minus_fixed | astra_medium | P1 | global | 0.00000 (5) | 0.00000 (5) | -20412.00000 (5) | 4.00000 (5) | 0.35081 (5) |
| adaptive_minus_fixed | astra_medium | P1 | conditional | -0.40000 (5) | 0.00000 (3) | -20401.20000 (5) | 5.80000 (5) | 0.63090 (3) |
| adaptive_minus_fixed | astra_medium | P1 | null | 0.00000 (5) | 0.00000 (5) | -20412.00000 (5) | 4.00000 (5) | 0.35115 (5) |

All signs are explicit: P1 − P0 and adaptive − fixed. Structure deltas use pairs with two terminal records, counting execution failures as no success; MSE/false-selection deltas require both episodes to complete successfully. Cost deltas retain failed-attempt costs and require known values. Missing pairs are omitted and listed by seed in metrics.json. These contrasts describe this small sample; model/prompt/strategy interactions prevent collapsing everything into one winner.

## Selection behavior

| Profile | Prompt | Data | Workflow | Null seen (n) | Pairwise used (n) | Stability used (n) | Fixed search seen (n) | Remaining actions (n) | Selected CV − best visible (n) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gpt4.1 | P0 | global | fixed | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 0.00036 (n=5) |
| gpt4.1 | P0 | global | adaptive | 0.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 6.00000 (n=5) | 0.00000 (n=5) |
| gpt4.1 | P0 | conditional | fixed | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) |
| gpt4.1 | P0 | conditional | adaptive | 0.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 5.40000 (n=5) | 0.00000 (n=5) |
| gpt4.1 | P0 | null | fixed | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 0.02130 (n=5) |
| gpt4.1 | P0 | null | adaptive | 0.50000 (n=4) | 1.00000 (n=4) | 0.00000 (n=4) | 0.00000 (n=4) | 5.00000 (n=4) | 0.02085 (n=4) |
| gpt4.1 | P1 | global | fixed | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 0.00139 (n=5) |
| gpt4.1 | P1 | global | adaptive | 1.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 4.80000 (n=5) | 0.00000 (n=5) |
| gpt4.1 | P1 | conditional | fixed | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) |
| gpt4.1 | P1 | conditional | adaptive | 1.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 5.00000 (n=5) | 0.00000 (n=5) |
| gpt4.1 | P1 | null | fixed | 1.00000 (n=4) | 0.00000 (n=4) | 0.00000 (n=4) | 1.00000 (n=4) | 0.00000 (n=4) | 0.02434 (n=4) |
| gpt4.1 | P1 | null | adaptive | 1.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 5.00000 (n=5) | 0.01050 (n=5) |
| sol_medium | P0 | global | fixed | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 0.00497 (n=5) |
| sol_medium | P0 | global | adaptive | NA (n=0) | NA (n=0) | NA (n=0) | NA (n=0) | NA (n=0) | NA (n=0) |
| sol_medium | P0 | conditional | fixed | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) |
| sol_medium | P0 | conditional | adaptive | NA (n=0) | NA (n=0) | NA (n=0) | NA (n=0) | NA (n=0) | NA (n=0) |
| sol_medium | P0 | null | fixed | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) |
| sol_medium | P0 | null | adaptive | 1.00000 (n=1) | 1.00000 (n=1) | 0.00000 (n=1) | 0.00000 (n=1) | 5.00000 (n=1) | 0.00000 (n=1) |
| sol_medium | P1 | global | fixed | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 0.00600 (n=5) |
| sol_medium | P1 | global | adaptive | 1.00000 (n=5) | 1.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 4.00000 (n=5) | 0.00600 (n=5) |
| sol_medium | P1 | conditional | fixed | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) |
| sol_medium | P1 | conditional | adaptive | NA (n=0) | NA (n=0) | NA (n=0) | NA (n=0) | NA (n=0) | NA (n=0) |
| sol_medium | P1 | null | fixed | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) |
| sol_medium | P1 | null | adaptive | 1.00000 (n=4) | 1.00000 (n=4) | 1.00000 (n=4) | 0.00000 (n=4) | 4.00000 (n=4) | 0.00000 (n=4) |
| astra_medium | P0 | global | fixed | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 0.00600 (n=5) |
| astra_medium | P0 | global | adaptive | 0.00000 (n=5) | 1.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 5.00000 (n=5) | 0.00600 (n=5) |
| astra_medium | P0 | conditional | fixed | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) |
| astra_medium | P0 | conditional | adaptive | 0.00000 (n=5) | 1.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 4.60000 (n=5) | 0.00000 (n=5) |
| astra_medium | P0 | null | fixed | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) |
| astra_medium | P0 | null | adaptive | 1.00000 (n=5) | 1.00000 (n=5) | 0.60000 (n=5) | 0.00000 (n=5) | 4.40000 (n=5) | 0.00000 (n=5) |
| astra_medium | P1 | global | fixed | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 0.00600 (n=5) |
| astra_medium | P1 | global | adaptive | 1.00000 (n=5) | 1.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 4.00000 (n=5) | 0.00600 (n=5) |
| astra_medium | P1 | conditional | fixed | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) |
| astra_medium | P1 | conditional | adaptive | 1.00000 (n=3) | 1.00000 (n=3) | 1.00000 (n=3) | 0.00000 (n=3) | 2.00000 (n=3) | 0.00000 (n=3) |
| astra_medium | P1 | null | fixed | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) |
| astra_medium | P1 | null | adaptive | 1.00000 (n=5) | 1.00000 (n=5) | 1.00000 (n=5) | 0.00000 (n=5) | 4.00000 (n=5) | 0.00000 (n=5) |

These behavioral means use successful episodes. Raw paths and failed attempts remain in TRAJECTORIES.md. Fixed evidence includes both exhaustive scans without calling diagnose, so its zero diagnose count does not mean the evidence was unavailable. Null seen refers to an exposed fitted null candidate, not a verbal mention. Selected CV minus minimum exposed CV is descriptive: simpler-model preferences can be defensible, and this gap is not an automatic error label. Remaining actions alone do not show wasted budget.

## Deterministic min-CV reference

| Data | Exact structure / available | Test MSE (n) | False condition (n) | False signal (n) |
| --- | --- | --- | --- | --- |
| global | 0/5 | 1.02057 (n=5) | 1.00000 (n=5) | NA (n=0) |
| conditional | 5/5 | 1.01927 (n=5) | NA (n=0) | NA (n=0) |
| null | 5/5 | 0.98439 (n=5) | 0.00000 (n=5) | 0.00000 (n=5) |

The auxiliary rule selects the minimum discovery-CV candidate already exposed by the fixed workflow, breaking ties by model ID. It is deduplicated across profiles/prompts for each seed and condition; reference scores use saved coefficients on regenerated matching held-out data, with no refitting. This reference is separate from the randomized model/prompt cells and has no incremental API cost. Coverage and repeated fixed-record consistency checks are in metrics.json.

## Spending ledger

| Stage | Present / planned | Calls | USD | Known USD | Cost complete episodes | Failed attempts |
| --- | --- | --- | --- | --- | --- | --- |
| development | 36/36 | 96 | NA | 4.982367 | 35/36 | 4 |
| formal | 180/180 | 458 | NA | 24.082685 | 176/180 | 24 |

Total reported cost for this experiment: NA USD; known partial sum: 29.065051 USD. Development costs are separate from primary outcomes. Prior pilots and superseded interface trials are outside this experiment's ledger.

## Explanation evidence audit

The offline reporting command in README.md regenerates EXPLANATION_AUDIT.jsonl and EXPLANATION_AUDIT.md from the complete restored records, including final explanations, public candidate cards, actual input summaries, actions, and remaining budgets. The published targeted review is EXPLANATION_REVIEW.md and explanation-review.json. Primary outcome metrics are deterministic. This reporting script does not judge explanations; separate assistant-assisted evidence review, when provided, is in EXPLANATION_REVIEW.md and explanation-review.json and is not part of the primary score. Numeric mentions and non-minimum-CV choices require review against the supplied evidence. All cases are included, not only successful or interesting ones.

Source hashes, configuration/prompt checks, missing cells, paired seed-level differences, and provider coverage are in metrics.json. Raw records are authoritative. Optional inventory reconciliation checked 216 progress rows and 0 summary rows; absent summaries are not claimed to have been checked. Historical absolute paths were not rewritten; the archive is read from its current location. No APIs or fitting were used by this reporter.
