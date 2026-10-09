# Stateful environments

When the agent acts on a world that persists — an MCP server, a sandbox, a database, a DAW, a browser — the benchmark acquires a second system that can be wrong. Most agentic-benchmark failures live here rather than in the tasks.

## Contents

1. [Reset and isolation](#1-reset-and-isolation)
2. [Snapshotting patterns](#2-snapshotting-patterns)
3. [Pinning the environment](#3-pinning-the-environment)
4. [MCP-specific concerns](#4-mcp-specific-concerns)
5. [Non-determinism and time](#5-non-determinism-and-time)
6. [Tool noise and retrieval](#6-tool-noise-and-retrieval)
7. [Generating tasks for a stateful domain](#7-generating-tasks-for-a-stateful-domain)
8. [Setup checklist](#8-setup-checklist)

---

## 1. Reset and isolation

ABC **T.4**: "Residual data or state are fully cleared between runs." This is the single most violated item, and it corrupts results in both directions — leftover state from a successful run can make the next task trivially pass, and leftover state from a failed run can make it impossible.

It also interacts with the statistics: Anthropic's guidance is to **isolate each trial from a clean environment** specifically so shared state cannot produce correlated failures or inflated scores. Correlated trials make pass^k and standard errors meaningless.

Patterns in use, roughly by cost:

| Pattern | Used by | Mechanics |
|---|---|---|
| **Per-sample container, destroyed after** | Inspect AI | Each sample gets its own sandbox; containers, images and networks removed when the task finishes. The default — use it unless you can't. |
| **Restart container from original image** | WebArena | Each site is a self-contained Docker image with code, DB and data and **no external volume mounts**; reset = stop and restart. Seconds to about a minute. |
| **Per-task fresh container** | AgentBench | Complex environments as Docker images, tasks split across workers. |
| **VM snapshot + hybrid setup scripts** | OSWorld | VM snapshots restore full machine state, but they **rejected per-example snapshots** (gigabytes each). Hybrid instead: boot → prepare files → run reprocessing commands. **302 distinct initial states** across 369 tasks. |
| **Fresh env + replay a reference trajectory** | τ²-bench | The target end state is *derived* rather than stored. See `scoring.md` §2. |
| **Deterministic replay from a fixed initial state + seed** | ARE / Gaia2 | No snapshot mechanism; apps hold state from an initial config, storage is in memory, every event logged. |

**The no-external-volume-mounts detail in WebArena matters more than it looks.** A volume mount is a channel through which state survives a container restart, which is exactly what you are trying to prevent. If your environment has one, you do not have reset; you have the appearance of reset.

For environments you cannot containerize — a DAW running on a host machine, hardware in the loop — you need an explicit save/restore of the full project or device state, plus a verification step that confirms the restore actually happened. Treat a failed restore as an aborted run, not a zero.

## 2. Snapshotting patterns

The decision is what counts as "the state."

- **Too narrow** and you miss side effects. If you snapshot only the clip you asked about, an agent that also detuned every other track passes.
- **Too broad** and incidental churn — timestamps, autosave counters, caches, log files, window positions — makes every run differ and nothing ever matches.

The workable shape:

```python
snapshot = {
    "scoped":     capture_target_region(env),   # what the task is about
    "ambient":    capture_everything_else(env), # for the unchanged-set assertion
    "excluded":   [...]                         # enumerated incidental churn
}
```

Enumerate exclusions explicitly rather than filtering by heuristic, and put the exclusion list in the benchmark card. It is a design decision: every excluded field is a side effect you have decided not to detect.

**Derive the target rather than storing it** where you can. τ²-bench replays a reference trajectory on a fresh environment at evaluation time, so the target end state is always consistent with the current environment version. Stored golden states rot the moment the environment changes; derived ones don't.

## 3. Pinning the environment

ABC **T.1** (tool versions specified), **T.2** (consistently accessible), **T.3** (handle API outages gracefully), **T.6** (setup does not change over time).

**T.6 is the one that silently destroys benchmarks.** OSWorld under-estimated an agent by ~28 points in one section because 13 of 46 Chrome tasks broke when the underlying websites changed. The benchmark was fine on release and wrong a year later, with no signal that anything had happened.

So:

- **Pin every version** — the MCP server package, the runtime it needs, the OS image, the model client library, and any host application. State them in the task prompt where the agent's behavior depends on them (T.1 is specifically about telling the *agent*, not just recording it).
- **No live external dependencies.** Mirror, snapshot, or mock. If a task needs the web, host the slice you need.
- **Detect and halt on outages** rather than scoring them as failures (T.3). A benchmark that reports an API outage as a model failure is actively misleading.
- **Build an environment health check** that runs before the suite, verifies every service responds and every version matches, and aborts loudly on mismatch. Cheap, and it is the only thing that catches drift.

If you deliberately choose freshness over reproducibility — MCP-Universe's dynamic evaluators fetch real-time ground truth at evaluation time — say so prominently. Results then are not comparable across time, and the card must say so.

## 4. MCP-specific concerns

**Pin both halves.** Many MCP integrations have a server package *and* a counterpart installed in the host application (a plugin, a remote script, an extension). The effective tool surface is the intersection. A capability-handshake layer — where newer tools check whether the installed counterpart supports them and degrade gracefully — means the package version alone does not determine behavior. Record both, and assert both at setup.

**Session state across calls.** If the server holds state between tool calls, the harness must keep the connection alive across the whole episode. In Inspect this is `mcp_connection()` — `react()` wraps it automatically, custom agents must not forget it. Forgetting produces a benchmark where every task fails for reasons unrelated to the model.

**Run the server inside the sandbox.** `mcp_server_sandbox()` makes the server part of the frozen environment rather than a moving external dependency. Install the server and its runtime at image build time, then run offline.

**Watch out for telemetry.** MCP servers increasingly ship usage telemetry, sometimes on by default, occasionally with opt-in dataset recording that uploads prompts and content. For a benchmark this is two problems: your runs pollute someone's dataset, and your results may be shaped by a feedback loop you didn't model. Check the server's telemetry documentation and disable it explicitly in the environment; record that you did.

**Tool surface is an independent variable.** Which tools you expose changes results — see §6. Pin the exposed set and report it. Inspect's `mcp_tools(server, tools=[...])` filters explicitly.

**Additive vs destructive writes.** Many MCP tools append rather than replace. An eval task phrased as "change X" will silently measure duplication unless the verifier accounts for the read-clear-write pattern the server actually requires. Read the tool docstrings, not just the names.

**Errors are part of the surface.** Timeouts, permission denials and empty results are common with real servers. Build tasks that deliberately trigger them and assert on the recovery — a timed-out write that the agent retries, producing a duplicate, is the canonical case a response-only scorer misses.

## 5. Non-determinism and time

**Repeated trials are the baseline control.** τ-bench uses pass^k; MCPToolBench++ defaults to 5 trials; MCPAgentBench uses avg@4; Gaia2 runs each split 3 times; MCPEval reports bootstrap CIs and paired tests. Pick k from your power analysis, not from habit.

**Fix what you can.** Seeds, temperature, model version strings. Note that WebArena ran at temperature 1.0 and reported only a temperature-0 run for one model — a reproducibility weakness it states itself. Don't lower temperature purely to reduce variance (see `statistics.md` §6); do record it.

**Time is a state variable.** ARE/Gaia2 has the most developed treatment: environment time advances independently of the agent, events fire on schedule whether or not the agent acts, and **the agent's own computation consumes simulated time** — so a slower model experiences a different world. Their simulated-generation-time mode pauses the simulation during generation and resumes with an offset equal to the real generation duration, which is how they survive API outages and rate limits without corrupting the scenario.

If your environment has any time dependence — scheduled events, rate limits, timeouts, anything with a clock — decide explicitly whether the agent's latency should affect outcomes. Both answers are defensible; an unexamined answer is not.

**Flaky tests are indistinguishable from model differences** at small n (ABC O.f.2). Run the oracle solution k times before the suite ships; any variance there is environment flakiness, and you should fix it or quantify it.

## 6. Tool noise and retrieval

Two findings that should shape how you scope the tool surface:

- **MCP-Universe:** connecting 7 servers (94 tools) instead of only the relevant ones **lowered performance**. Tool noise is a real effect, not a rounding error.
- **LiveMCPBench:** with 527 tools available, **retrieval errors account for nearly half of all failures.**

So if your benchmark exposes a large tool surface, you are substantially measuring tool retrieval, not task execution. That may be what you want — it is realistic — but it must be a stated design choice, not an accident.

The clean move is to **report both conditions**: a focused surface (only the tools the task needs) and a realistic surface (everything a user would plausibly have connected). The gap between them is itself a result, and a useful one.

## 7. Generating tasks for a stateful domain

Hand-annotating stateful tasks is expensive and error-prone — the SWE-bench Verified exercise found **38.3% of sampled tasks underspecified** and **61.1%** flagged for test problems, in a benchmark everybody was already using.

Three approaches that scale better:

**Compositional generation (τ²-bench).** Define atomic subtasks, each carrying an initialization function, a solution function, and an assertion function. Compose combinatorially. You get provable correctness and direct control over solution length. Best option when you can decompose the domain.

**Execution-verified generation (MCPEval).** An LLM writes candidate tasks from the server's tool specs; a frontier agent then *executes* each one against the live server. Successful runs become verified tasks with ground-truth trajectories; failures trigger refinement and retry. The ground truth is an executed trajectory, not an annotation. Their own stated limitation applies: automated verification can introduce false ground-truth labels on ambiguous or open-ended tasks, so sample and hand-check.

**Mined from real failures.** Bug trackers, support queues, your own transcripts. Difficulty is pre-validated by reality and construct validity comes free, because these are literally the things that went wrong. Slowest to collect, highest quality. This is what Anthropic's guidance recommends for the 20–50 task working tier.

Whichever you use, keep the **two-expert test**: a good task is one where two domain experts independently reach the same pass/fail verdict on a given attempt. If they don't, the task or the criteria are underspecified.

## 8. Setup checklist

```
[ ] Every version pinned: server, runtime, host app, plugin/counterpart, OS image
[ ] Versions stated in the task prompt where the agent needs them (T.1)
[ ] Environment health check runs before the suite and aborts on mismatch
[ ] No live external dependencies, or the trade-off is stated in the card
[ ] API outages halt the run rather than scoring as failures (T.3)
[ ] Fresh environment per trial, verified — not just requested
[ ] No volume mounts or other channels that survive reset
[ ] Snapshot scope defined: scoped / ambient / explicitly excluded fields
[ ] Unchanged-set assertions in place for side effects
[ ] Session state persists across tool calls within an episode
[ ] Telemetry disabled and recorded as disabled
[ ] Exposed tool set pinned and reported; both focused and realistic conditions run
[ ] Time dependence examined; agent latency's effect on outcomes decided deliberately
[ ] Oracle solution run k times to quantify environment flakiness
[ ] Agent cannot reach ground truth through the filesystem, network, env vars, or git history (T.5)
```
