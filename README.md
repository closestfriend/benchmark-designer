# benchmark-designer

A Claude skill for designing, red-teaming, and shipping rigorous evaluation suites for AI models and agents.

Built because the methodology exists — scattered across NeurIPS papers, harness docs, and a handful of adversarial audits — but nobody had packaged it. Searching for "benchmark designer" repos turns up almost nothing.

## The premise

Automated red-teaming drove **nine of ten** major agentic benchmarks — SWE-bench Verified, OSWorld, WebArena, Terminal-Bench, MLE-Bench and others — to near-perfect scores **without solving a single task**.¹ On τ-bench airline, an agent that returns empty responses scores 38%, beating a GPT-4o agent at 35%, because 38% of those tasks are intentionally unsolvable.²

These are the field's reference benchmarks, built by strong teams. The conclusion isn't "be careful" — it's that **the verifier is the benchmark**, and verifiers fail invisibly from the leaderboard.

So this skill inverts the usual order of work:

1. Write the claim before writing tasks
2. Design the verifier before the tasks
3. Build one task with an oracle solution and an adversarial solution
4. Attack the verifier before trusting it
5. Calibrate against four anchors — random, trivial, oracle, human
6. Only then scale, with power analysis deciding `n`
7. Report with intervals, cost, and a benchmark card

Hard rule: **ship nothing until the null agent has been run.**

## Install

```bash
git clone git@github.com:closestfriend/benchmark-designer.git ~/.claude/skills/benchmark-designer
```

Or package it for the claude.ai skill installer:

```bash
python -m zipfile -c benchmark-designer.skill benchmark-designer/
```

## Layout

```
SKILL.md                    the workflow — sizing, order of operations, repo layout
references/
  validity.md               ABC checklist verbatim, BetterBench, construct validity,
                            the eight exploit classes, an audit worksheet
  scoring.md                verifier design — end-state equivalence, the equivalence
                            relation, side effects, trajectory-as-diagnostic
  judges.md                 LLM-as-judge — bias numbers, what backfires, rubric design,
                            the meta-evaluation protocol
  statistics.md             power, paired comparison, Wilson/Bayesian intervals,
                            pass@k vs pass^k, saturation, format sensitivity
  harnesses.md              Inspect AI, promptfoo, and why not the others
  stateful-environments.md  reset, snapshotting, pinning, MCP specifics, time
  domains/
    music-arrangement.md    the honest state of music metrics + a worked Ableton design
  sources.md                every claim, with URLs and unverified-flags preserved
scripts/
  stats.py                  power/MDE, intervals, paired compare, pass@k, saturation
  scorer_redteam.py         drives degenerate outputs through your scorer
  judge_meta_eval.py        κ, Krippendorff's α, kappa deflation, position flip rate
assets/
  task-spec.schema.json     task schema; every field exists because its absence is a
                            documented failure mode
  benchmark-card.md         reporting template (ABC + BetterBench + Evaluation Cards)
```

## Scripts

Standard library only. Each runs under `python -I`.

```bash
python -I scripts/scorer_redteam.py --self-test
python -I scripts/stats.py --demo
python -I scripts/judge_meta_eval.py --self-test
```

`stats.py power` reproduces Miller's published worked example (n ≈ 969 to detect a
3-point difference at 80% power) exactly, which is the cheapest check that the
implementation is right.

## On subjective domains

Some constructs have no validated metric. Music arrangement is the clearest case: the
only published arrangement-quality instrument is **a single Likert item rated by nine
amateurs**.³ Objective symbolic metrics correlate with human judgment below 0.3, and
clustering on them classifies human-vs-AI music at chance.⁴

The skill's answer is not to invent a composite and call it quality. It's to decompose
until the verifiable part separates from the contested part — measure constraint
satisfaction well, report distribution metrics as drift rather than quality, and name
what remains unmeasured in the card.

That generalizes past music.

---

¹ [BenchJack](https://arxiv.org/html/2605.12673v1) ·
² [Establishing Best Practices in Building Rigorous Agentic Benchmarks](https://arxiv.org/abs/2507.02825), NeurIPS 2025 ·
³ [Multitrack Music Transformer](https://arxiv.org/pdf/2207.06983), ICASSP 2023 ·
⁴ [Armor](https://ar5iv.labs.arxiv.org/html/2108.12973), ACM MM '21

Full bibliography in [`references/sources.md`](references/sources.md), with the
unverified claims flagged as unverified.
