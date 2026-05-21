I conducted eight experiments to observe whether large language models can naturally detect interaction terms:

E0: Y = 2×X1 + 0.5×X2 - 1.5×X3 + 0.8×(X4×X5) + N(0,1)
E1: Y = 2×X1 + 0.5×X2 - 1.5×X3 + 2.0×(X4×X5) + N(0,1)
E2: Y = 2×X1 + 0.5×X2 - 1.5×X3 + 10.0×(X4×X5) + N(0,1)
E3: Y = 2×X1 + 0.5×X2 - 1.5×X3 + 0.8×(X1×X4) + N(0,1)
E4: Y = 2×X1 + 0.5×X2 - 1.5×X3 + 0.8×(X1×X2) + N(0,1)
E5: Y = X1 + X2 + 5×(X1×X2) + N(0,1)
E6: Y = X1 + X2 + 5×(X1×X2) + N(0,1)
E7: Y = X1×X2 + N(0,1)
E8: Y = X1 + X2 + 3×(X1×X2) + N(0,1)

These experiments can be divided into three groups: E0-E2, E3-E4, and E5-E8.

In E0-E2, I varied the coefficient of the interaction term while the variables inside the interaction term did not show strong linear correlation with Y. Across E0-E2, the interaction detection rate was zero.

In E3-E4, I tested interaction terms involving variables that already showed linear correlation with Y, but the models still failed to detect the interaction.

The most interesting pattern appears in E5-E8. Here I varied the balance between the linear terms and the interaction term. E7 was a pure interaction model, while E8 had both linear terms and a weaker interaction term. Neither produced a detected interaction. However, in E5, Gemini 2.5 Pro run2 suggested that X1×X2 was a plausible interaction candidate, and the evaluator scored it as positive. In E6, Gemini run1 positively guessed an interaction, but it guessed the wrong pair.

**My interpretation is that some models (Gemini), first search for variables with linear correlation to Y, and then only consider interactions among those variables (E0-E2,E7). However, if the linear signal is too strong, the model becomes satisfied with an additive linear explanation and stops searching for interactions (E3,4,8). Therefore, I guess interaction detection may only happen in a narrow regime: the relevant variables must be visible through linear correlation, but the linear model must still explain the data poorly enough to motivate the model to search for interactions.**

The next step I want to take is:

First, increase the number of models tested. So far, this behavior has only appeared in Gemini, so I need to check whether other LLMs show the same pattern.

If multiple LLMs show similar behavior, then I will systematically explore the coefficients to make this pattern more visible to see if I can prove that this is a phenomenon in how LLMs reason about interaction effects.
