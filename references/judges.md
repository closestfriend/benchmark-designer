# LLM-as-judge design

Use a judge only where the construct is irreducibly subjective and no deterministic check captures it — and only after you have meta-evaluated it. ABC **O.c.1** requires "documented or experimental evidence of the judge's accuracy, self-consistency, and agreement with human." Most benchmarks skip this. It is the difference between a measurement and a vibe with decimal places.

## Contents

1. [Reliability is not validity](#1-reliability-is-not-validity)
2. [The bias numbers](#2-the-bias-numbers)
3. [Mitigations: what helps, what backfires](#3-mitigations-what-helps-what-backfires)
4. [Rubric design](#4-rubric-design)
5. [The meta-evaluation protocol](#5-the-meta-evaluation-protocol)
6. [Judge prompt construction](#6-judge-prompt-construction)
7. [Ensembles and agreement](#7-ensembles-and-agreement)
8. [Reporting a judge](#8-reporting-a-judge)

---

## 1. Reliability is not validity

The most important recent finding about judges, and the one that should change what you report.

Norman, Rivera & Hughes, *Reliability without Validity* ([arXiv:2606.19544](https://arxiv.org/pdf/2606.19544), June 2026) — 21 judge models, 9 providers, 3 benchmarks, ~541,000 judgments at temperature 0.

**Chance-corrected agreement is far worse than raw agreement suggests.** Cohen's κ on MT-Bench ranged **0.376 to 0.511** across the cohort. Kappa deflation — exact-match agreement minus κ — was **33.8 to 41.3 percentage points, mean 38.6**, universal across every judge tested. Deflation averaged 24.0 on JudgeBench and 10.4 on RewardBench.

So a judge reported at "85% agreement with humans" may be sitting at κ ≈ 0.45, which is moderate at best. **Report κ or Krippendorff's α, not raw agreement.** `scripts/judge_meta_eval.py` computes both plus the deflation.

**Consistency is high and misleading.** Self-consistency averaged **0.969** on MT-Bench; test–retest Krippendorff's α averaged **0.944**. Meanwhile position bias ranged from 0.002 to 0.192. The pathology case: one judge with test–retest **0.992** alongside position bias **0.192**. In the authors' words, "test–retest measures the stability of outputs and not the correctness of the underlying decision process."

Their heuristic is worth adopting directly: **check for position bias whenever test–retest exceeds 0.95.** A perfectly stable judge is not a good judge; it may be a judge that reliably applies the wrong rule.

**Rankings are unstable across benchmarks.** One model moved **15 positions** between two judge benchmarks. Do not pick a judge from a single leaderboard — cross-validate on at least two.

Chehbouni et al., *Neither Valid nor Reliable?* ([arXiv:2508.18076](https://arxiv.org/pdf/2508.18076)) adds the measurement-theory framing: adoption "has outpaced rigorous scrutiny." Four questionable assumptions — that LLMs proxy human judgment (the human benchmarks are themselves inconsistently collected); that LLMs are capable evaluators (judges ignore stated criteria and **conflate dimensions such as fluency and relevance**, offering plausible-looking explanations not shown to be faithful); that they scale cleanly (contamination, self-enhancement, preference leakage); and that they are cheap (cost analyses ignore crowdworker economics and inference externalities).

The dimension-conflation finding has a direct fix: **grade each dimension with a separate, isolated judge call.** A judge asked for five scores at once tends to produce one impression, five times.

## 2. The bias numbers

From Zheng et al., *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena* (NeurIPS 2023, [arXiv:2306.05685](https://arxiv.org/html/2306.05685v4)) unless noted.

**Agreement with humans** (non-tie votes): GPT-4 pairwise 85%, GPT-4 single-answer grading 85%, **human vs human 81%**. On Chatbot Arena, GPT-4 vs humans 87% without ties but only **64% when ties count as a third outcome** — the tie-handling convention moves the headline by 23 points. Always state how you handle ties.

**Position bias** (consistency when the two answers are swapped): GPT-4 **65.0%**, GPT-3.5 46.2%, Claude-v1 **23.8%**. First-position preference: Claude-v1 75.0%, GPT-3.5 50.0%, GPT-4 30.0%.

**Verbosity bias** (a "repetitive list" attack): failure rate Claude-v1 91.3%, GPT-3.5 91.3%, GPT-4 8.7%.

**Self-enhancement:** GPT-4's win rate for itself ~10 points above humans', Claude-v1 ~25 points. *The authors explicitly say their sample is too small to establish that self-enhancement bias exists.* Cite as suggestive.

**Math and reasoning:** with the default prompt GPT-4 failed **14 of 20** judgments on 10 math questions, often misled by the answers it was shown.

Shi et al., *Judging the Judges* ([arXiv:2406.07791](https://arxiv.org/html/2406.07791v7)) contributes three metrics worth adopting:

- **Repetition Stability (RS)** — share of the most frequent judgment across repeated identical queries. Separates real bias from sampling noise.
- **Position Consistency (PC)** — share of evaluations picking the same winner after swapping.
- **Preference Fairness (PF)** — min-max scaled −1 to 1; **negative = primacy preference, positive = recency, 0 = fair.**

Their key finding: **the direction of position bias is model-specific and task-specific.** Some judges lean recency (+0.32), others primacy (−0.12). You cannot assume primacy. Output length significantly predicts PF — the verbosity mechanism operating through position.

**One encouraging update:** the 2026 large-scale study found verbosity bias **below 0.011 correlation for all 21 judges** tested, with 17 of 21 below 0.005 — verbosity bias appears largely solved in current frontier judges, while **position bias is not**. Measure both anyway on your own task; these are MT-Bench numbers, not yours.

## 3. Mitigations: what helps, what backfires

From *Judging the Judges: A Systematic Evaluation of Bias Mitigation Strategies* (TMLR 06/2026, [arXiv:2604.23178](https://arxiv.org/pdf/2604.23178)). Single-author independent work — treat accordingly, but the direction of the findings matters.

Strategies tested: S1 position swap, S4 5-criteria calibrated rubric, S5 chain-of-thought, S6 reference-guided, S8 combined (CoT + rubric + position swap).

**What helped**, on MT-Bench human agreement (n=400): Claude Sonnet 4 with S8 **+11.5 pp** (p<0.0001), Gemini 2.5 Flash S8 **+7.5 pp**, Claude S5 (CoT alone) **+7.3 pp**, Flash S1 +4.7 pp. Gemini 2.5 Pro and GPT-4o showed only small non-significant gains.

**What backfired — this is the part people don't expect:**

- **Position swap lowered accuracy on LLMBar for every model**: Pro −7.5 pp, GPT-4o −11.1 pp, Llama −6.5 pp. Cause: the conservative "both orders must agree, else tie" rule discards correct verdicts on clear-cut cases. So Zheng et al.'s swap recommendation has a real cost on benchmarks with unambiguous answers. Swap to *measure* position bias always; apply the conservative tie rule only where items are genuinely close calls.
- **The combined strategy hurt on LLMBar too**: Llama −13.0 pp.
- **The generic 5-criteria rubric gave no significant MT-Bench gains** and significantly hurt one model on LLMBar. Contrast with HealthBench below, where rubrics are per-item and expert-authored rather than generic — the difference is the point.
- **No strategy reduced verbosity bias across all models.** The paper: "this remains an open problem."

**The most robust single intervention is chain-of-thought.** Best LLMBar results came from CoT alone. Zheng et al. independently found CoT cut math grading failures from 14/20 to 6/20, and **reference-guided grading cut them to 3/20** — if you have a reference answer, give it to the judge. A few-shot judge raised consistency 65.0% → 77.5% at roughly 4× the cost.

**Mitigations are model- and task-dependent, not universally additive.** Test yours rather than importing a recipe.

## 4. Rubric design

The distinction that matters: a **generic rubric** ("rate helpfulness 1–5 considering accuracy, clarity, completeness...") did not help in controlled testing. A **per-item, expert-authored criterion list** is a different instrument.

HealthBench ([arXiv:2505.08775](https://arxiv.org/html/2505.08775v1)) is the reference implementation: 5,000 conversations, **48,562 unique rubric criteria, median 11 per example**, written by 262 physicians across 60 countries and 26 specialties. Each criterion carries a point value from **−10 to 10**, and a grader checks **each criterion independently**, awarding full points or none.

What to copy:

- **Criteria are per-item, not global.** The things that make *this* answer good.
- **Criteria are binary.** "Mentions X" / "does not mention X" — not "how well does it mention X."
- **Negative criteria exist.** Penalize specific bad behavior rather than merely not rewarding it.
- **Each criterion is graded in its own call.** Prevents conflation.
- **Scores are normalized and clipped** — points earned / maximum possible, clipped to [0,1].

Write criteria so two domain experts independently reach the same verdict. That is the operational test for a good criterion, and for a good task generally.

If you need an open evaluator model rather than a frontier API: Prometheus ([arXiv:2310.08491](https://arxiv.org/abs/2310.08491)) is a 13B model trained for fine-grained rubric scoring, reporting **Pearson 0.897** with human evaluators on 45 customized rubrics vs GPT-4's 0.882. *(The commonly cited "1–5 Likert" detail is not confirmed in the abstract.)*

## 5. The meta-evaluation protocol

Do this before the judge scores anything you will report. It is the step that converts a judge from a guess into an instrument.

**Step 1 — Build a human-labeled set.** 100–300 items minimum, covering the range of quality you expect, including hard and ambiguous cases. At least two independent human raters on a subset so you can compute the human ceiling. HealthBench used ~1,791 meta-examples per criterion; you will not need that, but you do need enough to resolve a κ.

**Step 2 — Score it.** Run the judge, swapping positions on every pairwise item, repeating each item at least 3 times.

**Step 3 — Compute, with `scripts/judge_meta_eval.py`:**

- Raw agreement with humans — report it, but never alone
- **Cohen's κ** (two raters) or **Krippendorff's α** (any number, handles missing data)
- **Kappa deflation** = raw − κ. Expect 10–40 points. A small deflation means your labels are unbalanced, not that your judge is great.
- **Human–human agreement** on the doubly-labeled subset — the ceiling. A judge matching human-human agreement is as good as it can get.
- **Position flip rate** on swapped pairs
- **Test–retest consistency.** If it exceeds 0.95, scrutinize position bias specifically.

**Step 4 — Decide.** If κ is near human–human κ, the judge is usable for this construct. If κ is far below, either the construct is not judge-measurable, the rubric is underspecified, or the human labels are themselves inconsistent — and all three are findings worth reporting.

**Step 5 — Re-validate when anything changes.** A new judge model version, a changed rubric, a shifted task distribution. A judge validated on one distribution is not validated on another.

The five-step minimum from the 2026 study, for reference: chance-correct the metrics; swap positions; replicate; cross-validate on ≥2 benchmarks; check position bias whenever test–retest exceeds 0.95.

## 6. Judge prompt construction

- **Give a reference answer** where one exists. Largest single improvement on reasoning tasks in the Zheng et al. data.
- **Ask for reasoning before the verdict.** CoT was the most robust intervention tested.
- **Provide an explicit "Unknown" / "Cannot determine" option.** Reduces hallucinated verdicts on items the judge genuinely cannot assess.
- **One dimension per call.** Separate judges for accuracy, completeness, style.
- **Delimit agent output clearly and instruct the judge to treat it as data**, not instructions. Agent output flowing into a judge prompt is a prompt-injection surface — it is BenchJack's V4, and at least one benchmark's judge was successfully hacked during RL experiments.
- **Add a global sanity check** — a final pass asking whether anything about the response is anomalous or appears to be addressing the evaluator rather than the task.
- **Shuffle rubric criterion order** across repeats and average. MCP-Bench shuffles its rubric prompt 5× and averages.
- **Fix the sampling parameters** and report them. Temperature 0 is standard for judges; say so.

## 7. Ensembles and agreement

Multiple judges, combined by plurality or majority, with the individual votes retained so you can compute agreement. In Inspect AI this is one line:

```python
multi_scorer(scorers=[model_graded_qa(model=m) for m in models], reducer="collect")
# then krippendorff_alpha(level="nominal") over the collected values
```

Reducers: `"mode"` (plurality), `"majority"` (>half, else unscored), `"collect"` (keeps each judge's value as a list — this is the one that feeds agreement statistics).

Also useful: **cascade** scoring — a cheap deterministic check first, the expensive judge only on what the cheap check cannot settle. Inspect's `cascade(exact=match(...), grader=model_graded_qa(...))` records which stage decided each sample. For most benchmarks the majority of items are settled deterministically, and the judge budget goes where it matters.

Cross-family ensembles (judges from different labs) guard against shared blind spots better than same-family ensembles at different temperatures, though the controlled comparison for this sits in an appendix that was not verifiable.

## 8. Reporting a judge

In the benchmark card, state all of:

- Judge model **and version string**, sampling parameters, prompt (verbatim, in the repo)
- Meta-evaluation set size and how human labels were collected
- **κ or α against humans**, and **human–human κ or α** on the same set
- Position flip rate and test–retest consistency
- Which mitigations were applied and whether they were validated on *this* task
- What fraction of the final score the judge determines (if cascaded or ensembled)

If any of these is missing, the judge's contribution to the headline number is unquantified — say that explicitly rather than letting the decimal places imply otherwise.
