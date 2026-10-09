# Harnesses

Verified API surfaces as of late 2026. Where a name could not be confirmed from current documentation, it is flagged — check before relying on it.

## Quick comparison

| Framework | Multi-turn tool use | Stateful envs | Sandboxing | MCP | Trajectory scoring | Stats built in |
|---|---|---|---|---|---|---|
| **Inspect AI** | Yes (`react()`, agents) | Yes (sandbox + custom scorer) | Yes (docker, k8s, +6) | **First-class** | Custom scorer over `TaskState` | Yes — clustered SE, Wilson CI, Krippendorff |
| **promptfoo** | Yes | Bring your own | No | Proxy only | **Richest built-in assertions** | Minimal |
| lm-evaluation-harness | No | No | No | No | No | Basic |
| OpenAI Evals / Graders | Via completion fns | No | No | No | `sample.output_tools` + `multi` | No |
| Langfuse | Tracing only | No | No | No | Not documented | Score analytics |
| Braintrust | Yes (traces/spans) | Bring your own | No | Guidance only | Span- and trace-level scorers | Some |
| HELM | No | No | No | No | No | Yes |

**Default to Inspect AI for agentic work.** Use promptfoo when you already have an environment and want assertions. Don't build on lm-eval-harness for tool use, on OpenAI's hosted Evals (being deprecated), or on HELM (**entered maintenance mode 1 June 2026**).

---

## Inspect AI (UK AI Security Institute)

[inspect.aisi.org.uk](https://inspect.aisi.org.uk/) · [repo](https://github.com/UKGovernmentBEIS/inspect_ai)

A `Task` combines **dataset + solver + scorer**.

### Core surface

| Component | API |
|---|---|
| **Dataset** | `hf_dataset()`, `json_dataset()`, `csv_dataset()`, `FieldSpec` for field mapping; samples carry `input` / `target` |
| **Solver** | A single `generate()` up to a full tool-using agent |
| **Scorer** | `includes()`, `match()` (begin/end/any/exact, `numeric=True`), `pattern()`, `answer()`, `exact()`, `f1()`, `choice()`, `math()`, `model_graded_qa()`, `model_graded_fact()`, `perplexity()`, `target_perplexity()`, `multi_scorer()`, `cascade()`, `precomputed_scores()` |
| **Tool** | `bash()`, `todo_write()`, custom tools, **MCP tools** |
| **Sandbox** | `sandbox="docker"`; also `local`, and external `k8s`, `daytona`, `modal`, `ec2`, `proxmox`, `vagrant`, `openshell` |
| **Agents** | `react()` (built-in reason-act-observe loop), Multi Agent, **Agent Bridge** (runs Claude Code / Codex CLI / Gemini CLI inside an eval), Human Agent, Deep Agent |
| **Decorators** | `@task`, `@scorer`, `@metric`, `@score_reducer` |
| **Log viewer** | `inspect view` |

### MCP support — the reason this is the default

From `inspect_ai.tool`:

- `mcp_server_stdio(command, args, env)` — local stdio server
- `mcp_server_http(url)` — remote HTTP server; supports `execution="remote"`, but **remote servers can't be used under an approval policy**, since Inspect never sees those tool calls
- **`mcp_server_sandbox()`** — a stdio server running *inside* the sandbox. This is what you want for a reproducible benchmark: the server is part of the frozen environment.
- `mcp_tools(server, tools=[...])` — filter which tools the agent sees. Essential for tool-noise experiments.
- **`mcp_connection()`** — context manager that **persists server state across calls**. `react()` wraps this automatically; custom agents must `async with` it themselves. If your MCP server holds session state, forgetting this silently breaks every task.

Sandbox MCP servers need a Dockerfile installing the server and its runtime (Node for `npx` servers, etc.) at **build time**, then run with `--offline`.

### Sandboxing

Declared via the `sandbox` parameter (not `sandbox_env`) as a string, a `(type, config)` tuple, or a `SandboxEnvironmentSpec`. Precedence: eval → Task → Sample, except that a sample's own config file wins when its type matches. Per-sample `files` are copied in, then a `setup` bash script runs.

**Footgun:** generated compose configs set `network_mode: none`. A custom compose config **replaces** that default and must set isolation explicitly — otherwise you have just granted network access and quietly violated T.6.

API: `sandbox().exec(cmd, input, cwd, env, user, timeout, ...)` → `ExecResult`; `write_file()`, `read_file()`, `connection(user=...)`, `sandbox_default("name")`. Limits: `read_file()` raises above 100 MB; `exec()` output is capped at 10 MB and **front-truncated silently** by built-in providers — the docs warn not to rely on exceptions to detect overflow. Override via `INSPECT_SANDBOX_MAX_READ_FILE_SIZE` / `INSPECT_SANDBOX_MAX_EXEC_OUTPUT_SIZE`.

Cleanup is automatic; `inspect sandbox cleanup <provider>` and `--no-sandbox-cleanup` for debugging.

### Custom scorers — your state-matching hook

```python
@scorer(metrics=[accuracy(), stderr()])
def my_scorer():
    async def score(state: TaskState, target: Target) -> Score:
        ...
    return score
```

`Score` fields: `value`, `answer`, `explanation`, `reason`, `metadata`. `Score.unscored(...)` yields a NaN score excluded from metrics; returning `None` creates no score entry at all. `Value` can be `str | int | float | bool`, a sequence of those, or a **mapping** — use the mapping form to return several named sub-scores from one scorer. Constants: `CORRECT`="C"→1.0, `INCORRECT`="I"→0.0, `PARTIAL`="P"→0.5, `NOANSWER`="N"→0.0.

Scorers can call models **and inspect the sandbox** — that is how you implement end-state equivalence. Read the environment, compute the equivalence relation, return the score.

Useful default behavior: `pattern`/`answer` set `reason="invalid_response_format"` when the pattern is absent, and empty output sets `reason="no_response"` — which makes the WebArena empty-reply failure visible rather than silently scored.

> Not verified: a dedicated trajectory *scorer* API. Trajectory scoring is done by writing a custom scorer over `TaskState` (including `state.messages`).

### Metrics and reducers

Metrics: `accuracy()`, `mean()`, `var()`, `std()`, **`stderr(cluster="key")`** (clustered SEs), `bootstrap_stderr()` (1000 samples default), `ci()` (95% Student-t by default; `level=`, `method="bootstrap"`), **`ci_wilson()`** (preferred for binary), `frequency()`, `categorical()`, **`krippendorff_alpha(level="nominal"|"ordinal"|"interval")`**, `grouped(metric, key)`, `perplexity_per_token`, `perplexity_per_seq`.

Clustered SE requires declaring the metric at the **Task** level, since it overrides the scorer's built-in metrics.

Epochs: `Epochs(count, reducer)`. Registered reducer names: `mean`, `median`, `mode`, `majority`, `max`, `pass_at_{k}`, `pass_k_{k}`, `at_least_{k}`, `collect`. `pass_at_{k}` = at least one of k correct; `pass_k_{k}` = all k succeed; `majority` = more than half agree else unscored. Lists work: `Epochs(5, ["at_least_2", "at_least_5"])`. CLI: `--epochs`, `--epochs-reducer`, `--no-epochs-reducer`.

> Naming caveat: the reference page and metrics page use different conventions for `pass_at` / `pass_k` / `pass_at_k`. Test the reducer string before relying on it.

### Multiple scorers

```python
Task(dataset=dataset,
     solver=[system_message(SYSTEM_MESSAGE), generate()],
     scorer=[model_graded_qa(model="openai/gpt-4"),
             model_graded_qa(model="google/gemini-2.5-pro")])

multi_scorer(scorers=[model_graded_qa(model=m) for m in models], reducer="collect")
cascade(exact=match(location="exact"), grader=model_graded_qa(model=grader_model))
```

`headline_metric` on the Task selects the headline number. `cascade` runs stages in order, stops at the first that settles the sample, and records `decided_by` in metadata — cheap deterministic check first, expensive judge only on the remainder.

### eval() parameters worth knowing

Limits: `message_limit`, `token_limit`, `turn_limit`, `time_limit`, `working_limit`, **`cost_limit`**. Concurrency: `max_samples`, `max_tasks`, `max_subprocesses`, `max_sandboxes`, `max_connections`. Errors: `fail_on_error`, `continue_on_fail`, `retry_on_error`, `score_on_error`, `debug_errors`. Generation: `temperature`, `max_tokens`, `top_p`, `seed`, `reasoning_effort`, `response_schema`. Also `eval_set()`, `eval_retry()`, `score()`.

**Cost accounting is first-class** — `cost_limit` and the logs give you the cost-per-task number that *AI Agents That Matter* argues is mandatory.

### Scanners

`inspect_ai` ships **scanners** that review transcripts for refusals, **evaluation awareness**, and environment misconfiguration — separate from task-success grading. The closest thing to a built-in validity-flaw detector. Run them.

### inspect_evals

[repo](https://github.com/UKGovernmentBEIS/inspect_evals) — a library of evaluations built on Inspect, maintained by Generality Labs with contributions from UK AISI, Arcadia Impact and Vector Institute. SWE-bench via a `swe_bench` extra; Cybench and GDM capability evals are Docker-heavy. Terminal-Bench 2.0 and SWE-Bench Pro live in a separate Inspect Harbor package. BFCL v4 is **not** implemented (open issue #1026).

---

## promptfoo

[docs](https://www.promptfoo.dev/docs/intro/)

The best off-the-shelf assertion vocabulary, especially for tool use. Bring your own environment — no sandbox or environment-provisioning abstraction was found.

- **Tool / function-call:** `is-valid-function-call`, `is-valid-openai-function-call`, `is-valid-openai-tools-call`, **`tool-call-f1`**
- **Trajectory (deterministic):** `trajectory:tool-used`, `trajectory:tool-args-match`, `trajectory:tool-sequence`, `trajectory:step-count`. Model-graded: `trajectory:goal-success`
- **Trace / agent:** `trace-span-count`, `trace-span-duration`, `trace-error-spans`, `skill-used`
- **Custom code:** `javascript`, `python`, `ruby`, `webhook` — your rubric-as-code hook
- **Model-graded:** `llm-rubric`, `g-eval`, `similar`, `classifier`, `moderation`, `factuality`, `model-graded-closedqa`, `answer-relevance`, `context-faithfulness`, `context-recall`, `context-relevance`, `conversation-relevance`, `select-best`, `max-score`
- **Deterministic:** `equals`, `contains`, `is-json`, `cost`, `is-refusal`, `perplexity`, `guardrails`

Mechanics: prefix any type with `not-` to negate; `assert-set` groups assertions with a threshold. Multi-turn via `options.storeOutputAs`, an implicit `_conversation` variable, and session IDs. `assert` and `vars` are test-case properties, not top-level config keys. Runs as CLI, library, or in CI.

---

## The rest, briefly

**lm-evaluation-harness (EleutherAI).** Declarative YAML tasks; `output_type` is `generate_until` | `loglikelihood` | `loglikelihood_rolling` | `multiple_choice`. Its genuinely interesting feature is **filter pipelines**: model outputs live in `Instance.resps`, and named pipelines collapse them into `filtered_resps`, so one run with `repeats: 64` can report `score-first`, `maj@64`, and `maj@8` side by side (`regex` → `majority_vote` → `take_first`). Very broad backend support. **No multi-turn tool use, no sandbox** — wrong tool for agentic work.

**OpenAI Evals / Graders.** The open-source repo is not archived but **does not accept custom-code evals**, and the hosted Graders product is being deprecated. Grader types: `string_check`, `text_similarity`, `score_model`, `python`, `multi`. For tool use, tool calls appear as `sample.output_tools` and the documented pattern combines a `string_check` on function name with one on arguments — which the docs themselves warn under-rewards `1` vs `1.0`. Don't build here.

**Langfuse.** Traces, Datasets, Experiments, Scores, Evaluators (LLM-as-judge, decision-model, code), Annotation Queues, plus a GitHub Action that fails a PR on a score threshold. Observability-first; evaluation built on live traces. No sandboxing and **no documented trajectory or tool-call scoring abstraction**.

**Braintrust / autoevals.** `Eval(name, { data, task, scores })`. Scorer families: LLM-judge (`Factuality`, `ClosedQA`, `Summarization`, `SQL`, `Translation`, `Moderation`, `Security`, `Battle`, `Humor`), RAGAS-derived, string/similarity (Levenshtein, embedding similarity, BLEU, ROUGE, METEOR, BERTScore), numeric, JSON diff. Span- and trace-level scorers. Their write-up on MCP evals is the best vendor articulation of the decomposition in `scoring.md` §6. *(The autoevals docs reachable were ~2 years stale; treat the scorer list as indicative.)*

**HELM (Stanford CRFM).** **Maintenance mode since 1 June 2026.** Pipeline: Scenario → Instance → DataPreprocessor → Adapter → ScenarioState/RequestState → Executor → Metric → Stat, orchestrated by RunSpecs. Historically valuable for its multi-metric framing (efficiency, bias, toxicity alongside accuracy) — worth reading for the idea, not for building on. *(Code-level class names could not be confirmed from current docs.)*

---

## Named benchmarks worth reading as design references

Not to run — to steal from.

| Benchmark | Steal this |
|---|---|
| **τ²-bench** | Replay a reference trajectory on a fresh environment → hash the end state. Read/write tool split. Compositional task generator with init/solution/assertion functions per atomic subtask. The domain template (`data_model.py`, `tools.py`, `environment.py`, `tasks.json`, `policy.md`) is the cleanest layout for a new stateful domain. |
| **MCP-Universe** | 84 evaluators in three classes — Format (4), Static (32), Dynamic (48, fetching real-time ground truth at eval time). Explicitly rejects LLM judging for state-dependent tasks. Also: connecting 7 servers (94 tools) instead of only the relevant ones **lowered** performance — the tool-noise effect, worth measuring deliberately. |
| **MCPEval** | Self-verifying task generation: an LLM writes tasks from tool specs, a frontier agent executes them, successful runs become verified tasks **with ground-truth trajectories**. Ships bootstrap CIs and paired tests — rare. Its own stated limitation: automated verification can introduce false ground-truth labels on ambiguous tasks. |
| **LiveMCPBench** | Retrieval-first agent loop (Route / Execute / Response) over 527 tools. **Retrieval errors account for nearly half of all failures** — if your benchmark has many tools, you are probably measuring retrieval. |
| **OSWorld** | Getter/metric split with a library of 134 reusable evaluation functions. Includes **30 deliberately infeasible tasks** and awards partial credit for correctly predicting infeasibility. |
| **WebArena** | Self-hosted sites as Docker images with no external volume mounts; reset = restart from image in seconds to a minute. Per-role auth via pre-cached cookies. |
| **Gaia2 / ARE** | Verifies **write actions** against oracle writes; reads unverified. Checks tool-name counts, **causality** (parent actions matched first), and **timing within a tolerance window**. Argument checks split into hard (exact, for IDs) and soft (LLM judge). Environment time advances independently of the agent and the agent's own computation consumes simulated time. |
| **MCPEvol-Bench** | Tests **schema drift** — 123 servers in multiple versions, 11 mutation operators simulating interface changes. Frontier models declined ~14% on evolved servers. If your MCP server will change, test this. |
