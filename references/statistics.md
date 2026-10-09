# Statistics for evals

Most eval reporting omits uncertainty entirely: **14 of 24** benchmarks surveyed neither ran multiple evaluations of the same model nor reported significance or uncertainty. This is the cheapest rigor available — the math is a dozen lines and `scripts/stats.py` implements all of it.

## Contents

1. [Standard errors](#1-standard-errors)
2. [Small evals: don't use the CLT](#2-small-evals-dont-use-the-clt)
3. [Clustered standard errors](#3-clustered-standard-errors)
4. [Paired comparison — the highest-leverage practice](#4-paired-comparison--the-highest-leverage-practice)
5. [Power and how many tasks you need](#5-power-and-how-many-tasks-you-need)
6. [Variance reduction](#6-variance-reduction)
7. [pass@k vs pass^k](#7-passk-vs-passk)
8. [Saturation and discriminative power](#8-saturation-and-discriminative-power)
9. [Difficulty calibration and item selection](#9-difficulty-calibration-and-item-selection)
10. [Format sensitivity: the error bar you can't shrink](#10-format-sensitivity-the-error-bar-you-cant-shrink)
11. [Reporting checklist](#11-reporting-checklist)

---

## 1. Standard errors

The frame from Miller, *Adding Error Bars to Evals* ([arXiv:2411.00640](https://arxiv.org/pdf/2411.00640)): treat eval questions as **drawn from an unseen super-population**. The score you got is an estimate of the score you'd get on all possible questions of this kind, and it has sampling error.

```
SE_CLT = sqrt(Var(s) / n),   Var(s) = (1/(n-1)) * sum_i (s_i - s_bar)^2
SE_Bernoulli = sqrt(s_bar * (1 - s_bar) / n)      # binary scores
95% CI: s_bar +/- 1.96 * SE
```

Bootstrapping is unnecessary unless you have a complicated sampling scheme or estimator. `SE_Bernoulli` is conservative when scores are fractional (partial credit, F1).

## 2. Small evals: don't use the CLT

Bowyer, Aitchison & Ivanova, *Don't Use the CLT in LLM Evals With Fewer Than a Few Hundred Datapoints* (ICML 2025, [arXiv:2503.01747](https://arxiv.org/pdf/2503.01747)). CLT intervals "systematically fail to provide valid uncertainties" on small benchmarks:

- SE is **zero** when every item passes or every item fails — the interval collapses to a point, which is obviously wrong.
- Intervals extend outside [0,1].
- At **N=100, nominal 95% CLT intervals achieve only 92.5% coverage.**

Use instead:

- **Single model, IID items:** the **Wilson score interval**, or a Bayesian Beta-Bernoulli posterior **Beta(1 + S, 1 + N − S)**. Both are in `scripts/stats.py interval`. They prefer these over Clopper–Pearson, which is "overly conservative (too wide) in practice."
- **Model comparison:** Bayesian intervals on the difference or odds ratio, which let you state **P(model A > model B)** directly — usually what the reader actually wants.
- **Non-linear metrics (F1):** Bayesian intervals with a Dirichlet posterior over confusion-matrix counts.

Inspect AI ships `ci_wilson()` for binary scores and recommends it over its generic `ci()`.

## 3. Clustered standard errors

When items are drawn in related groups — several questions on one passage, several tasks in one repo, several arrangements of one song — observations within a group are correlated and the naive SE understates uncertainty.

```
SE_clustered = sqrt( SE_CLT^2 + (1/n^2) * sum_c sum_i sum_{j!=i} (s_ic - s_bar)(s_jc - s_bar) )
```

Measured ratios of clustered to naive SE: **DROP 3.05, MGSM 1.88, RACE-H 1.10.** Ignoring clustering on DROP understates the standard error threefold.

This bites agentic benchmarks hard, because task families are the norm — several variants of the same underlying scenario. METR handles it differently and well: weight each task by **1/√(family size)** and bootstrap hierarchically over families → tasks → runs (10,000 samples). If your tasks come in families, do one of these two things.

In Inspect: `stderr(cluster="family")`, declared in the Task's `metrics` since it overrides the scorer's defaults.

## 4. Paired comparison — the highest-leverage practice

When comparing two models on the same tasks, compare **question-level paired differences**, not the two population summaries. The covariance term shrinks the standard error, often dramatically:

```
Var_paired = Var_unpaired - 2 * Cov(x_A, x_B) / n
SE_paired  = sqrt( SE_A^2 + SE_B^2 - 2 * SE_A * SE_B * Corr(s_A, s_B) )
```

Correlation between two models' per-item scores is typically 0.3–0.7, so this is not a marginal gain. `scripts/stats.py compare` does it.

The practical consequence: a 2.5-point difference with correlation 0.50 can be clearly significant while a 3.1-point difference with correlation 0.64 is not, depending on the variances. **Report the paired CI on the difference, not two separate CIs and an eyeball.** Overlapping marginal CIs do not imply a non-significant difference.

## 5. Power and how many tasks you need

Before running anything, ask whether the eval *can* detect the difference you care about.

```
n = (z_{alpha/2} + z_beta)^2 * (omega^2 + sigma_A^2/K_A + sigma_B^2/K_B) / delta^2
omega^2 = Var(x_A) + Var(x_B) - 2*Cov(x_A, x_B)
```

where δ is the difference you want to detect, K is trials per question, and ω² is the between-question variance of the paired difference.

Worked: ω² = 1/9, δ = 0.03, α = 0.05, β = 0.20 ⇒ **n ≈ 969 questions.**

That number is the reason most leaderboard movements are not real. If you have 40 tasks and are ranking five models three points apart, the ranking is noise. Either accept that you are doing directional work, or get more tasks.

`scripts/stats.py power` solves for n given δ, and `--mde` inverts it to give the minimum detectable effect at your actual n. Run the MDE calculation on every benchmark you build and **put the number in the card** — it tells readers which differences to believe.

## 6. Variance reduction

```
Var(mu_hat) = (Var(x) + E[sigma_i^2]) / n
```

Two terms: between-question variance (irreducible without more questions) and within-question variance from sampling (reducible by repeating).

Resampling each question K times gives Var(s_i) = σ²_i/K. The returns diminish fast: K=2 cuts variance by 1/3, K=4 by 1/2, K=6 by 5/9, **asymptotic limit 2/3**. So repeats help, but cannot substitute for more questions. In one worked example with n=198, raising K from 1 to 10 lowered the MDE from 13.2% to 7.5% — real, but you would have done better with more tasks.

Using next-token probabilities as the score removes conditional variance entirely, where the task admits it.

**Do not lower sampling temperature to reduce variance.** It shifts variance into the between-question term or injects bias. If you want to evaluate the model at temperature 0.7, evaluate it at temperature 0.7.

## 7. pass@k vs pass^k

These answer different questions and diverge sharply.

- **pass@k** — probability at least one of k attempts succeeds. For tasks where you can verify and retry.
- **pass^k** — probability **all** k attempts succeed. For tasks where reliability matters and a single failure is a failure.

75% per-trial over 3 trials is **~42% pass^3**. An agent that looks good at pass@1 can be unusable in production, and pass^k is what surfaces that.

Unbiased estimators from c successes in n runs:

```
pass^k   = E_task[ C(c, k) / C(n, k) ]
pass@k   = E_task[ 1 - C(n-c, k) / C(n, k) ]
```

Both in `scripts/stats.py passk`. In Inspect, `Epochs(5, ["pass_at_3", "at_least_2"])` gives several reducers over the same runs.

**Isolate each trial from a clean environment.** Shared state across trials produces correlated failures or inflated scores and makes these estimators meaningless. This is ABC T.4.

## 8. Saturation and discriminative power

A benchmark is saturated when top models "can not be reliably distinguished by their performance scores." Formalized in *When AI Benchmarks Plateau* ([arXiv:2602.16763](https://arxiv.org/pdf/2602.16763)):

```
n_eff  = n^0.5                           # effective test size
R_norm = (s_1 - s_k) / SE_delta,  k = 5  # top-model spread vs eval noise
S_index = exp(-R_norm^2)   in [0,1]      # higher = more saturated
```

Bins: very low <0.01, low 0.01–0.3, moderate 0.3–0.7, high 0.7–0.9, very high ≥0.9.

Of 60 text benchmarks studied, **29 showed high or very high saturation (≥0.7), 14 very high (≥0.9)**. They distinguish **stagnation** (top models indistinguishable) from **saturation** (indistinguishable *and* near the empirical ceiling) — worth keeping separate, since the remedies differ.

Their recommendations: increase resolution (more and harder items, stratified reporting by subskill) so differences exceed noise; integrate dynamic updates and **rotating hidden subsets**; report uncertainty-aware statistics; and **define lifecycle criteria — revision, expansion, retirement — in advance**, before anyone is attached to the leaderboard.

`scripts/stats.py saturation` computes the index. Run it at release and periodically after.

## 9. Difficulty calibration and item selection

**The ceiling problem, quantified.** An IRT analysis of 11 benchmarks and 41,871 items found that **the hardest items rarely exceed difficulty ~1.0 while top models have estimated abilities above 3.0** ([arXiv:2505.15055](https://arxiv.org/html/2505.15055v3)). Item saturation was widespread, notably on GSM8K and ARC-C. Items with unusually high guessing-rate parameters were flagged as a possible contamination signal.

**Item volume does not confer quality.** Selecting **1,000 items by Fisher information** gave Kendall's τ up to **0.9048** against a reference ranking, versus **0.2381** using all items. A smaller, better-chosen set ranked models better than the full set.

**100 well-chosen items can estimate a full benchmark to ~2%.** tinyBenchmarks ([arXiv:2402.14992](https://arxiv.org/html/2402.14992v2)) uses 100 examples per scenario with IRT-based anchor selection and reports ~2% average estimation error; on MMLU (~14K examples), **100 curated examples (<1%) gives under 2% error**. Their anchor-selection strategies: stratified random sampling, correctness-based clustering, and IRT-based clustering (fit IRT, use parameters as low-dimensional embeddings, k-means, take the example nearest each centroid, weight by cluster share).

**An alternative to IRT: anchor difficulty to human completion time.** METR ([arXiv:2503.14499](https://arxiv.org/pdf/2503.14499v1)) measures each task's difficulty as the **geometric mean of successful human baseline times**, collected from 800+ baselines totalling 2,529 hours, with tasks written blind to model performance. Then fit:

```
P(success) = sigmoid( (log h_model - log t_task) * beta_model )   # 50% time horizon
```

This is far more interpretable to a stakeholder than a latent ability parameter — "this model completes tasks that take a human an hour" lands in a way "ability 3.1" does not. Their reported doubling time was ~212 days (95% CI 171–249). Their own caveats are worth repeating: errors are highly correlated across models, so **the trend is more reliable than any single model's point estimate**; conditioning on success biases task lengths downward.

**Practical calibration without IRT:** report random, trivial, oracle, human, and frontier anchors (see SKILL.md §4), aim for a headline pass rate in a band that discriminates among the models you care about, and check that you have items at several difficulty levels rather than a pile at one.

## 10. Format sensitivity: the error bar you can't shrink

Two results that bound how precisely any single-format score can be read.

Sclar et al. (ICLR 2024, [arXiv:2310.11324](https://arxiv.org/pdf/2310.11324)): accuracy varies by **up to 76 points** across semantically equivalent prompt formats for one model, with a **median spread of 7.5 points** across models and settings at only 10 sampled formats per task — a lower bound. Across 320 formats × 53 tasks on one model: spread up to 56 points, median 6.4. A format good for one model is not good for another. *(The commonly quoted "804 formats" figure does not appear in the paper; the largest set reported is 320.)*

Su et al. ([arXiv:2510.05152](https://arxiv.org/pdf/2510.05152)): testing 30 non-alphanumeric ASCII **example delimiters** — one character — produced max−min spreads on MMLU of 18.3 to 29.4 points for open models and **45.63 points for GPT-4o (78.59 with "@" down to 32.97 with "?")**. On one ICL task a model ranged from ~20% to ~80%. **Delimiter choice can reorder model rankings** — any model in their set could be put in the lead by changing only the delimiter. Brittleness did not shrink with scale.

The mitigation that worked: **explicitly state the delimiter in the prompt**, which improved average performance by 1.5 to 27.9 points. Absent that, "\n" and "!" were most consistently strong.

Two implications for your benchmark:

1. **Report the format verbatim** in the repo, including delimiters and whitespace. Without it your results are not reproducible even with the same model.
2. For a published benchmark, **report a range across a few plausible formats** rather than a point estimate. No amount of sampling shrinks this particular error bar.

## 11. Reporting checklist

```
[ ] n, and the MDE at that n
[ ] Epochs per task, and the reducer used (mean / pass@k / pass^k)
[ ] Interval method (Wilson / Bayesian / CLT) and why
[ ] Clustered SE if items come in families; or family weighting
[ ] Paired CI on every model-vs-model difference claimed
[ ] Random, trivial, oracle, human, frontier anchors
[ ] Saturation index
[ ] Cost: tokens, wall-clock, dollars per task
[ ] Model version strings, temperature, max_tokens, top_p, seed
[ ] Prompt format verbatim, delimiters included
```

The sampling-parameter line is nearly free and almost universally skipped: across ~50k reported (model, benchmark, metric) triples, **max_tokens was missing in 95.6% and temperature in 93.9%**; for agentic results, evaluation plan and limits were missing **100%** of the time.
