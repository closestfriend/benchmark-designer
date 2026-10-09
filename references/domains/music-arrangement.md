# Domain: music composition and arrangement

Read this when evaluating a model's ability to compose, arrange, or operate a DAW. It covers the honest state of the measurement literature, what is computable from symbolic data, and a worked benchmark design for an Ableton-MCP arrangement eval.

## Contents

1. [The headline: arrangement quality is unmeasured](#1-the-headline-arrangement-quality-is-unmeasured)
2. [What the negative results actually say](#2-what-the-negative-results-actually-say)
3. [The three-way split that makes this tractable](#3-the-three-way-split-that-makes-this-tractable)
4. [Symbolic metrics you can compute from a MIDI or DAW-state dump](#4-symbolic-metrics-you-can-compute-from-a-midi-or-daw-state-dump)
5. [Metrics that require rendered audio](#5-metrics-that-require-rendered-audio)
6. [The arrangement-specific metrics that do exist](#6-the-arrangement-specific-metrics-that-do-exist)
7. [Human evaluation protocols in this field](#7-human-evaluation-protocols-in-this-field)
8. [Worked design: an Ableton MCP arrangement benchmark](#8-worked-design-an-ableton-mcp-arrangement-benchmark)
9. [ableton-mcp specifics](#9-ableton-mcp-specifics)
10. [Open gaps worth claiming](#10-open-gaps-worth-claiming)

---

## 1. The headline: arrangement quality is unmeasured

There is no validated metric for arrangement quality. The field has well-specified, implemented metrics for **pitch, rhythm, harmony**, and partially for **repetition structure**. Arrangement — instrument role, track density, section contrast, register separation, voice leading — is measured either not at all, by a single subjective Likert item, or by a one-off metric invented in one paper and never reused.

The state of the art in arrangement-quality measurement, concretely: Multitrack Music Transformer (ICASSP 2023) asked **nine music amateurs** to rate a single item, with this exact wording from footnote 2:

> **arrangement** — "Are the instruments used reasonably? Are the instruments arranged properly?"

That is the instrument. If you need to measure arrangement quality, **you are building it, not adopting it.** Which is a genuine research opportunity, but it means the benchmark must be honest about what it is doing.

## 2. What the negative results actually say

Cite these when someone proposes a composite "musical quality score."

- **Armor** (ACM MM '21, [arXiv:2108.12973](https://ar5iv.labs.arxiv.org/html/2108.12973)) — a direct meta-evaluation. Four objective metrics (mir_eval, MGEval, area-between-melody-curves, BLEU) correlated with human similarity scores **all below 0.3**. Clustering on MGEval features classified human vs AI music at **50.4% — chance.** And critically: **metrics aligned better for single-track than multi-track music.** The arrangement case is precisely where metrics are weakest.
- **FAD vs human preference** ([arXiv:2503.16669](https://arxiv.org/html/2503.16669v1)) — on an open dataset of 2,520 pairwise human judgments across 7 models, **FAD reached Kendall τ = 0.14** while the best metric tested (MAD, MAUVE over MERT embeddings) reached **τ = 0.62**. FAD was the weakest metric reported.
- **FAD's embedding dependence** ([arXiv:2403.17508](https://arxiv.org/html/2403.17508v1)) — Spearman correlation with human perception ranges from **below 0.1 (VGGish)** to **above 0.5 (PANNs-WGM-LogMel)** depending purely on the embedding. VGGish, the default in most published FAD numbers, "predicts musical quality only slightly better than chance." *Caveat: that study is environmental audio, so the winning embedding should not be assumed to transfer to music.*
- **Aesthetic predictors** ([arXiv:2504.21815](https://arxiv.org/html/2504.21815v1)) — Meta Audiobox Aesthetics vs 2,515 human pairwise preferences: musicality accuracy 48.3%–62.3%, Spearman **≤ 0.258**, with one axis **at chance on musicality and negative on fidelity**. The authors describe overall agreement as very poor.
- **The framing to adopt** — Sturm & Ben-Tal: comparing output statistics with training data is "a first-order sanity check" with "limited relevance" to usefulness for music practice. And they reject the music Turing test outright: fooling listeners is "ultimately weak and uninformative."

Together: **symbolic and audio distribution metrics are regression detectors and distribution sanity checks, not quality scores.** Use them that way and say so.

## 3. The three-way split that makes this tractable

Decompose until the verifiable part separates from the contested part.

| Layer | What it is | How to score | Status |
|---|---|---|---|
| **Constraint satisfaction** | Did it do what was asked? 8 bars, in A minor, kick on the downbeat, bass below C3, four distinct sections, hi-hats replaced not duplicated | Deterministic checks on the symbolic state | **Fully verifiable.** And this is where agents actually fail. |
| **Distribution sanity** | Does the output sit in a plausible region of feature space relative to a reference corpus? | Symbolic feature distances, reported as drift not quality | **Regression detector only.** |
| **Preference** | Is it good? | Pairwise human judgment, with inter-rater reliability reported | **Honest but expensive and noisy.** |

For an agentic DAW benchmark, layer 1 carries most of the signal, because the failures are overwhelmingly mechanical: wrong bar counts, notes written to the wrong clip, duplicated material from additive writes, sections that don't actually differ, instruments out of range, the arrangement never leaving the session view. Those are all checkable, and an agent that fails them is not making interesting aesthetic errors.

Report layer 1 as the headline. Report layer 2 as drift. Report layer 3 only if you actually run it, with its reliability. State in the card that arrangement quality as such is not measured.

## 4. Symbolic metrics you can compute from a MIDI or DAW-state dump

No audio rendering required. Grouped by what they tell you.

**Pitch and harmony** — `muspy.metrics`: `pitch_range`, `n_pitches_used`, `n_pitch_classes_used`, `polyphony`, `polyphony_rate(threshold=2)`, `pitch_in_scale_rate(root, mode)`, `scale_consistency`, `pitch_entropy`, `pitch_class_entropy`. ([docs](https://muspy.readthedocs.io/en/latest/metrics.html))

**Rhythm** — `muspy.metrics`: `empty_beat_rate`, `empty_measure_rate`, `drum_in_pattern_rate(meter)`, `drum_pattern_consistency`, `groove_consistency(measure_resolution)`.

> `groove_consistency` is 1 − mean Hamming distance between onset vectors of **neighboring** measures. It is a local-steadiness measure and will *penalize* a legitimate fill, drop, or section boundary. For arrangement work that is useful rather than broken: **the derivative of groove consistency is a section-boundary signal.**

**The canonical feature framework** — Yang & Lerch, *On the evaluation of generative models in music*, Neural Computing and Applications 32(9):4773–4784, 2020 ([DOI](https://doi.org/10.1007/s00521-018-3849-7); toolbox [mgeval](https://github.com/RichardYang40148/mgeval)). Features: PC (pitch count), PCH (12-D pitch class histogram), PCTM (12×12 transition matrix), PR (pitch range), PI (average pitch interval), NC (note count), IOI (average inter-onset interval), NLH (note length histogram), NLTM (note length transition matrix), each with a `/bar` variant.

Their **relative measurement** procedure is the part that matters: compute pairwise distances within a set (intra-set) and between sets (inter-set), build histograms, KDE with a Gaussian kernel and Scott's-rule bandwidth, then compare the training-set intra-set PDF against the train-vs-generated inter-set PDF using **KLD** or **OA (overlapping area**, bounded [0,1], proposed because KLD is unbounded and asymmetric). *Caveat from the paper: the method as published accepts only monophonic fixed-length MIDI melodies.* And mgeval depends on `python-midi`, which is Python-2-era — expect to port or substitute.

**Structure, computable from note data:**

- **Similarity Error (SE)** — Museformer ([arXiv:2210.10349](https://arxiv.org/pdf/2210.10349)). Bar similarity is Jaccard over note sets, `l_ij = |N(i) ∩ N(j)| / |N(i) ∪ N(j)|`, with notes matching iff pitch, duration and within-bar onset position are all identical. `SE = (1/T) Σ_t |L̂_t − L_t|` over T=40 bar intervals, comparing the generated average similarity curve to the training-set average. **The most directly reusable structure metric for a DAW dump** — note sets per bar, no audio, no MATLAB. Their empirical structure prior is also useful on its own: a bar is most similar to the previous 2 bars and the previous 4th bar and its multiples (default structure-related bars: previous 1, 2, 4, 8, 12, 16, 24, 32).
- **Pitch-class histogram entropy (H₁, H₄), grooving pattern similarity (GS), chord progression irregularity (CPI)** — Wu & Yang, *The Jazz Transformer on the Front Line* (ISMIR 2020, [arXiv:2008.01307](https://arxiv.org/pdf/2008.01307), code [MusDr](https://github.com/slSeanWU/MusDr)). GS uses a **64-dimensional binary onset vector** per bar; CPI is the percentage of unique chord trigrams. **These take event-token sequences, not general MIDI** — you will need a tokenizer.
- **Distinct n-grams (DN)** and over-repetition flags — Compose & Embellish ([arXiv:2209.08212](https://arxiv.org/pdf/2209.08212)). DN is the percentage of distinct pitch n-grams on the skyline melody, at short (3–5 notes), mid (6–10) and long (11–20) windows. Their over-repetition criterion is concrete and directly usable as a failure check: **one bar repeated exactly and consecutively more than 6 times, or two neighboring bars repeated more than 4 times.**
- **Tension curves** — `partitura.musicanalysis.estimate_tonaltension` returns **`cloud_diameter`** (maximal tonal distance among simultaneous notes in the spiral array), **`cloud_momentum`** (distance between successive centers of effect), and **`tensile_strain`** (distance from the current key's center of effect). Herremans & Chew, TENOR 2016. **The only ready-made symbolic time-varying "arc" measure** — three tension curves straight from note data.

**Instrumentation and texture** — jSymbolic 2.2 ([site](https://jmir.sourceforge.net/jSymbolic.html)) extracts **246 unique features / 1,497 feature values** from MIDI and MEI across seven categories, two of which are **Instrumentation** (which instruments are present and emphasized) and **Texture** (number of independent voices, how they interact, relative importance). **The closest thing to an off-the-shelf arrangement feature set.** Java; McKay, Cumming & Fujinaga, ISMIR 2018.

**Multi-track metrics from MuseGAN** (AAAI 2018, [arXiv:1709.06298](https://arxiv.org/pdf/1709.06298)): **EB** (ratio of empty bars), **UPC** (used pitch classes per bar, 0–12), **QN** (ratio of "qualified" notes — no shorter than three time steps / a 32nd; low QN means overly fragmented), **DP** (ratio of notes in 8- or 16-beat patterns), and **TD** (tonal distance, Harte et al. 2006) which measures harmonicity **between a pair of tracks** — larger TD implies weaker inter-track harmonic relations. **TD is the only widely-circulated genuinely inter-track metric.** They validate it by shuffling the training data and confirming TD increases, which is a clean validation pattern worth copying.

**Symbolic distribution distance** — Frechet Music Distance ([arXiv:2412.07948](https://arxiv.org/html/2412.07948v2), toolkit [frechet-music-distance](https://github.com/jryban/frechet-music-distance)) fits Gaussians to CLaMP 1/2 embeddings of ABC or MIDI. *No published correlation with human judgment that could be verified* — treat as drift detection only.

## 5. Metrics that require rendered audio

FAD (any embedding), FAD∞ and per-song FAD (toolkit [fadtk](https://github.com/microsoft/fadtk)); KL-divergence over AudioSet tagger labels; CLAP score, MuQ-MuLan, CLaMP 3 audio branch; MMD/KAD, MAD, MAUVE, Precision/Recall/Density/Coverage; Audiobox Aesthetics, SongEval, DNSMOS; PEAQ, ViSQOL, SNR/SDR; **Structureness Indicators (SI) via fitness scape plot**, as published; and all human listening tests.

Given §2, audio-domain distribution metrics buy you little for an agentic arrangement benchmark and cost a rendering pipeline. Skip them unless the construct genuinely requires timbre or mix quality. If you do use FAD, **do not use VGGish embeddings** — use CLAP or MERT, and report which.

**One Group-B metric worth porting into Group A:** a fitness scape plot needs a self-similarity matrix, and nothing requires that SSM to come from audio chroma. An SSM built from per-bar symbolic feature vectors — PCH, onset vectors, per-track activity masks — runs through the same scape-plot algorithm (MusDr ships a MATLAB-free `run_python_scapeplot.py`), giving SI without rendering and allowing **per-track SI**, which no published work computes. That is an open gap, not a solved problem.

## 6. The arrangement-specific metrics that do exist

The best set is in Zhao et al., *Structured Multi-Track Accompaniment Arrangement via Style Prior Modelling* ([arXiv:2310.16334](https://arxiv.org/pdf/2310.16334)):

- **DOA (Degree of Arrangement)** — for each track k, average over bars the **KL divergence of that track's 12-D PCH from the piano reduction's PCH** to get d_k; **DOA is the standard deviation of d_k across tracks.** Higher = more differentiated instrumentation. **The only published metric measuring differentiation *between* tracks as such.**
- **Chord Accuracy** — fraction of arrangement chords matching the lead sheet, by root and quality at 1-beat granularity.
- **Faithfulness (statistical)** — cosine similarity between input and the output's reduction on 12-D PCHs.
- **ILS (Inter-phrase Latent Similarity)** — ratio of average similarity between **same-type phrases** to average across all phrases, over VAE latents of 2-measure segments. Variants for pitch, rhythm, chords, texture. Needs a pretrained texture VAE.

The paper is explicit that it defines **no** separate instrumentation metric and **no** inter-track coherence metric; inter-track cohesion is assessed subjectively only.

From METEOR ([arXiv:2409.11753](https://arxiv.org/pdf/2409.11753)), three directly reusable quantities:

- **Rhythmic intensity** — share of sub-beats with at least one onset. Their stand-in for note density.
- **Polyphonicity** — average sounding notes per sub-beat.
- **% out-of-range notes per instrument** — they report 0.0%–4.8% against real instrument ranges. **This is a simple, usable arrangement-correctness check** and the only register measure published.

They also note that melody identification is done by **skyline** (highest average pitch per bar), which the authors themselves call "a compromise." Treat any role-assignment metric built on skyline as approximate.

**For the three things people most want to measure — instrument role consistency, section contrast, voice leading — there is no citable metric in any paper surveyed.** Nearest proxies: role → skyline plus jSymbolic's Texture category; section contrast → the derivative of `groove_consistency`, plus subjective "Boundary Clarity" and "Phrase Similarity" constructs from Wang et al.'s whole-song work; voice leading → nothing. jSymbolic's melodic- and vertical-interval categories are the raw material, but nobody has assembled them into a voice-leading score.

## 7. Human evaluation protocols in this field

**Don't use MUSHRA.** It requires a hidden reference that is by definition the best stimulus. Generative arrangement has no reference — the human-composed version is a *different valid answer*, not an upper bound — so the scale's anchoring semantics don't apply. MUSHRA also has documented **stimulus spacing bias** and **range equalizing bias** producing discrepancies of **up to 22%** (Zielinski et al., AES Preprint 7179). Every music-generation paper surveyed uses plain Likert or pairwise forced choice instead.

**The consolidated dimension set** comes from Chu et al., CIKM '22 ([DOI](https://doi.org/10.1145/3511808.3557235)), who reviewed 40 models, found 39 unique subjective metrics, and reduced them to nine: **Overall, Creativity, Naturalness, Melodiousness, Richness, Rhythmicity, Correctness, Structureness, Coherence.** The categories overlap, and the paper reports **no inter-rater reliability statistic** — three authors coded by discussion with no agreement measure. Use the taxonomy; don't inherit the methodology.

**Realistic sample sizes in this literature:** 9 raters (MMT), 13–24 (METEOR), 23 (Zhao et al.), 15 (Compose & Embellish), 57 (Wang et al.), 144 (MuseGAN). Analysis is typically within-subject repeated-measures ANOVA with 95% CIs, Wilcoxon signed-rank, or t-tests.

**No music-generation paper surveyed reports Krippendorff's α or Cohen's κ.** You should. The closest human–human agreement figure available anywhere nearby is from speech: **r = 0.596** on a concrete axis and **0.253** on a subjective one. Expect your noise floor to be in that range and report it, or the reader cannot tell signal from rater disagreement.

**A self-reported bias worth internalizing.** The Anticipatory Music Transformer authors note that instructing workers to pick the "more conventionally musical" clip, combined with top-p 0.95 sampling that "is less likely to introduce a new instrumental part," **favors conservative arrangement.** The rating question shapes what wins. Write the question for the thing you actually want.

**LLM and audio-LLM judges:** there is no validated judge for music quality, let alone arrangement quality. GPT judging annotation errors in symbolic MIR tasks scored **59.7%–65.2%** — above chance, far from reliable. Audio-LLM judges are validated only for *speech style*, where Gemini-2.5-Pro reached Pearson 0.640 against a human–human ceiling of 0.596 on one axis, and both tested judges showed self-enhancement bias. Two separate 2025 surveys of music-generation evaluation found no MLLM-as-judge work for music at all. **If you use a judge here, you are doing novel methodology and must meta-evaluate it** (see `judges.md` §5).

## 8. Worked design: an Ableton MCP arrangement benchmark

A concrete instantiation of the SKILL.md workflow for the case of "test models on arrangement/composition work through the Ableton MCP."

### Construct

> "A model that scores high on this can take a musical instruction expressed in producer language and realize it correctly as structured MIDI and arrangement state in a DAW, without collateral damage to the project. A low score means it cannot. This informs whether to let a model drive a DAW session unsupervised."

Note what this claim does **not** say: nothing about whether the result is good music. That is deliberate, and it goes in the card.

### Scoring design

**Layer 1 — end-state equivalence on the project snapshot.** The equivalence relation needs music-aware tolerances, each a design decision to record:

```python
def equivalent(actual, target):
    # order-invariant over note sets within a clip
    # velocity tolerance: +/- N (state N; 0 if the task is about velocity)
    # timing tolerance: quantized to the task's grid
    # transposition: NOT invariant by default — if the task names a key, key is part of the spec
    # track order: invariant; track identity by name, not index
    # device parameters: only those the task names
```

Derive the target by **replaying a reference solution on a fresh session** rather than storing a golden project file — Live versions and device defaults change, and a stored target rots.

**Layer 1b — constraint assertions.** Most of the real signal. Per task, a list of binary checks:

- Bar/beat counts correct; clip lengths as specified
- All notes within the requested scale / key
- Named instrument on the named track; track names as specified
- Register constraints (bass below a stated pitch, lead above one) — the out-of-range-notes check
- Section boundaries exist where specified; **sections actually differ** (onset-vector Hamming distance between section-representative bars above a threshold)
- Over-repetition flags clear (no bar repeated identically more than 6 consecutive times)
- For "modify X" tasks: note count did not simply increase — catches additive-write duplication

**Layer 1c — the unchanged set.** Every track, clip, device parameter and mixer setting outside the task's scope must be byte-identical to the initial snapshot, with incidental churn enumerated. Report side-effect violations as a separate number.

**Layer 2 — drift.** Symbolic feature distances against a small reference corpus of human arrangements in the same idiom: PCH/NLH distributions, Museformer SE, groove consistency, DOA, TD between track pairs. Reported as drift, labelled as not-a-quality-score.

**Layer 3 — preference.** Optional, pairwise, with κ or α reported, and only if you will actually run enough raters to resolve anything.

### Task set shape

Build from **real session failures** — things you have actually watched a model get wrong. Suggested axes, roughly ascending in difficulty:

1. **Atomic writes** — create a track, name it, write a four-bar MIDI clip with a specified pattern.
2. **Read-modify-write** — "swap the hi-hats to 16ths but keep the kick." Directly tests whether the model knows writes are additive and clears first. Expect this to be where cheap models die.
3. **Structural** — "duplicate the verse to the arrangement at bar 33 and make the chorus busier." Tests arrangement-view operations, not just session clips.
4. **Constraint satisfaction under ambiguity** — "make the drop hit harder" with an explicit rubric of what counts (density up, register separation maintained, nothing outside key).
5. **Negative controls** — tasks where the correct action is to do nothing or to ask. Without these you cannot detect an agent that always edits.
6. **Error recovery** — a task where a tool call will fail or time out; assert that the retry did not duplicate material.

### Baselines, all four

- **Null agent** — does nothing. On any task whose initial state is already partly correct, this will score above zero, and you need to know by how much.
- **Random-edit agent** — makes arbitrary valid MCP calls. Catches verifiers that reward activity.
- **Oracle** — a scripted reference solution per task, which must score 100%.
- **Human producer** — one or two people doing the tasks by hand in Live, timed. Also gives you METR-style human-time difficulty anchors, which are far more interpretable to a musician than a latent ability score.

### Harness

Inspect AI. `mcp_server_sandbox()` is unavailable here because Live runs on the host, so you will be running the MCP server against a real Ableton instance — which means the environment health check in `stateful-environments.md` §3 is not optional, and reset must be explicit (load a template `.als`, verify it loaded, run, snapshot, discard). Budget for the fact that this does not parallelize the way a container does.

Scoring goes in a custom `@scorer` that reads the session snapshot and returns a **mapping** `Value` with named sub-scores (`state_match`, `constraints`, `side_effects`, `drift`) so you can report them separately rather than collapsing to one number.

## 9. ableton-mcp specifics

Notes on [ahujasid/ableton-mcp](https://github.com/ahujasid/ableton-mcp), the most developed option. Verify against the current source — this moves.

**Architecture:** two halves. An Ableton **Remote Script** running a socket server inside Live, and the **MCP server** that connects to it over JSON-over-TCP. Requires Live 10+, Python 3.8+, `uv`. Installed with `uvx --from ableton-mcp ableton-mcp-install-script`, then selected as a Control Surface with Input and Output set to None. MIT licensed.

**Tool surface**, grouped:

- *Read* — `get_session_info`, `get_remote_script_info`, `get_track_info`, `get_clip_notes`, `get_device_parameters`, **`get_session_snapshot(include_notes, include_params)`**, `get_browser_tree`, `get_browser_items_at_path`, `get_arrangement_clips`
- *Create* — `create_midi_track`, `create_audio_track`, `set_track_name`, `create_clip`, `create_audio_clip`, `set_clip_name`, `delete_clip`
- *Notes* — `add_notes_to_clip(track_index, clip_index, notes)` where each note has `pitch`, `start_time`, `duration`, `velocity`, `mute`; `clear_notes_from_clip`
- *Devices* — `load_instrument_or_effect`, `load_drum_kit`, `set_device_parameter`
- *Transport* — `set_tempo`, `fire_clip`, `stop_clip`, `start_playback`, `stop_playback`
- *Arrangement* — `switch_to_arrangement_view`, `set_arrangement_time`, **`duplicate_to_arrangement(track_index, clip_index, destination_time)`** (beats; Live 11/12), `set_arrangement_clip_name`, `create_locator`

**Three things that directly shape benchmark design:**

1. **Writes are additive.** `add_notes_to_clip` only appends. The documented modify loop is `get_clip_notes` → edit → `clear_notes_from_clip` → `add_notes_to_clip`. **An eval that scores "change the hi-hats" without accounting for this will silently measure duplication** rather than modification. Make it an explicit assertion.
2. **`get_session_snapshot` is a state oracle, already built.** Its docstring describes it as capturing a full project snapshot for trajectory recording — session metadata, every track with mixer, devices, session clips and arrangement clips, optional MIDI notes and device parameters — "used to version musical state S_t → S_{t+1}." That is your state-matching verifier handed to you.
3. **A capability handshake means the tool surface depends on the installed Remote Script version**, not just the package version. Newer tools call `require_capability()` and degrade to a "missing" string on older scripts. **Pin and assert both halves** — this is ABC T.1/T.2/T.3 in one.

**Telemetry — handle before you run anything.** Anonymous telemetry (install ID, session ID, which tools ran, success, duration) is **on by default**. Dataset recording (prompts, MIDI notes, track and clip names, device settings, which may be published as an open dataset used to train music-production models) is **off by default and opt-in**, with consent stored in `~/.ableton-mcp/consent.json`. For a benchmark, disable both: `ABLETON_MCP_DISABLE_TELEMETRY=true` covers both tiers; `ABLETON_MCP_DISABLE_DATASET=true` disables dataset recording only and overrides any stored grant. Record in the card that you did.

**Alternatives.** [ideoforms/AbletonOSC](https://github.com/ideoforms/AbletonOSC) exposes the Live Object Model over OSC (listens on 11000, replies on 11001) with namespaces for application, song, view, track, clip_slot, clip, scene, device, and midimap. **The better substrate if you want coverage or state observation** — it has `start_listen`/`stop_listen` for property-change push plus beat events and clip playing position, which lets you observe state transitions without polling, and a bulk `/live/song/get/track_data`. Beta stability, LOM coverage incomplete, zero-indexed channels. Several MCP wrappers over AbletonOSC exist; coverage is mostly undocumented and at least one secondary source lists two as unmaintained.

**No public benchmark for DAW or Ableton MCP agents exists.** This is open ground.

## 10. Open gaps worth claiming

If the goal includes publishable contribution rather than only an internal eval, these are the unoccupied positions found in this survey:

- **The first DAW-agent benchmark.** Nothing public exists. The pieces are assembled above.
- **Per-track structureness.** Porting fitness scape plots onto symbolic SSMs built from per-bar track-activity vectors gives per-track SI, which no published work computes.
- **A section-contrast metric.** Section contrast is currently measured only subjectively ("Boundary Clarity," "Phrase Similarity"). A metric over onset-vector and PCH distance between section-representative bars is straightforward and nobody has published one.
- **A voice-leading score.** jSymbolic's melodic- and vertical-interval features are the raw material; no one has assembled them.
- **A meta-evaluation of arrangement metrics** in the style of Armor but targeted at arrangement rather than similarity. Armor's finding that metrics align worse for multi-track than single-track is an invitation nobody has taken up.

Each of these needs the same validation move to be credible: **collect human judgments and report correlation with them**, rather than proposing a metric and asserting it captures something. That is precisely the step the existing literature skips, and why its metrics correlate below 0.3.
