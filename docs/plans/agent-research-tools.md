# Agent Research Tools — The Deterministic Instrument Bench

> **Status — proposal (2026-06-29).** This is a design proposal for the *tool
> surface* an `Actor` (human now, agent later) uses to produce ground-truth
> research results. It is the missing substance behind the roadmap's
> **"Agent-Ready Execution Surface"** (`docs/plans/roadmap-next-steps.md` §0.7.0,
> *not yet built* — the repo's `0.7.x` was an auth-principal refactor, a different
> scope that reused the number). It depends on, and extends, the primitives in
> `docs/primitives.md`, the ledger semantics in `docs/research-git.md`, and the
> stage skeleton in `docs/research-flow.md`. Nothing here is implemented yet.

## 1. The ask, in one line

Give the research agent **an encyclopedia and a power calculator** — tools that
return *deterministic* results, especially about numbers and facts, so the agent
is not guessing where it could be computing or looking up. And let us **see** the
agent's thinking and its results.

This document turns that intuition into a concrete, licensed, build-ordered list
of tools, and grounds each one in the data model we already have.

## 2. Why "deterministic" is the organizing principle

A hallucinated number cannot be a citizen of an append-only ledger. It cannot be
pinned, hashed, re-run, or **blamed** (`research-git.md` §Blame). A *deterministic*
result can: a CAS integral, a Lean proof, a CODATA constant, an Arb interval bound
— each is reproducible and independently checkable, which is exactly what lets it
become a content-addressed `Artifact` or a pinned `Evidence` row.

So these tools are **not a feature bolted onto the agent**. They are the only way
an agent can manufacture the kind of result the ledger is built to hold. The
organizing axis of the whole bench is therefore *how deterministic is the output*,
and we grade every tool on it.

### 2.1 The evidence grade ladder (new concept — should attach to every Claim/Evidence)

What the ledger most needs to record is **how strongly a claim is grounded** — an
*epistemic* ladder that maps straight onto the central `Claim`/`Evidence` primitives:

| Grade | Meaning | Produced by | Strength |
|---|---|---|---|
| **A — Formally verified** | A machine-checked proof or certificate; the claim is *proven* | Lean/Coq proof check, Z3/cvc5 unsat + certificate | Settles a universal |
| **B — Exact & deterministic** | An exact symbolic derivation or rigorous/correctly-rounded computation — reproducible and exact, but not a general proof | SymPy, exact rational arithmetic, Arb intervals, `gmpy2`, CODATA constants | Strongly supports; exact for specific cases |
| **C — Numerical / empirical** | Floating-point computation, simulation, fitted data, or finitely many examples — supports within a stated tolerance; can *falsify* a universal but never *prove* one | SciPy, Monte-Carlo, MD/PDE/DFT, dataset fits | Supports / falsifies, never proves |
| **D — Heuristic / LLM-only** | The model's unaided reasoning, no tool in the loop | the agent itself | The baseline the bench exists to climb *out of* |

The whole purpose of the bench is to move a claim **D → C → B → A**: an LLM hunch
gains numerical support, hardens to exact computation, and — where possible — closes
with a formal proof. A claim's confidence (`primitives.md`: *"explainable through
evidence and validation history, not a naked score"*) is exactly this ladder made
legible.

**A secondary, mechanical axis** records *how* a computed (B/C) result reproduces, so
the ledger stays honest about floating-point/GPU non-determinism: *bit-verifiable*
(identical everywhere) · *env-pinned* (bit-identical only on a pinned image / BLAS /
thread-count / seed — most single-thread CPU numerics) · *tolerance-only* (statistical,
never bit-identical — GPU MD, MPI PDE). Grade-A and exact Grade-B results are inherently
bit-verifiable; the distinction bites *inside* Grade C. **The ledger must not pass a
tolerance-only Grade-C run off as a Grade-A fact** — that overstates a finding, the
opposite of what a provenance ledger is for. (Retrieved *external* evidence — §III —
sits off this ladder: it's graded by source authority + pin quality, not by computation.)

The single highest-leverage data-model change this implies (see §7) is recording the
**grade on every Claim / Evidence / Artifact**.

## 3. How the tools fit the ledger we already have

Three load-bearing facts about the current model make this clean:

1. **The provenance hook already exists.** `Checkpoint.tool_invocations`
   (`research-git.md` §Commit) is specified as *"for each tool-agent called: name,
   version, inputs, outputs"* and is already carried as free-form JSON on the
   checkpoint today. That tuple **is** the determinism contract: `(tool, version,
   inputs) → output`, hashable for blame. We mostly need to *schema-enforce* it.

2. **The tool-agents are already named.** `research-flow.md` reserves black-box
   tool-agents per stage — `math-formalizer`, `numerical-runner`, `proof-checker`,
   `dataset-fitter`, `literature-search`, `prior-art-lookup`, `constraint-extractor`,
   `statistical-validator`, `contradiction-checker`, `merge-resolver`. This proposal
   fills those names with real implementations; it does **not** invent a new
   vocabulary.

3. **Tools produce existing primitives, not new ones.** Every tool run lands as an
   `Artifact` (a derivation, plot, notebook, proof object), an `Evidence` row (a
   pinned external fact or a computed result used to support/weaken a claim), or a
   `Validation` (a machine-checked pass/fail). Tools compose with the checkpoint
   chokepoint (`services/checkpoints.py`) like validation and branching already do
   — they never write the ledger directly.

### 3.1 The four families and where they land

| Family | The metaphor | Evidence grade | Produces | Fills tool-agents | Research-flow stage |
|---|---|---|---|---|---|
| **I · Compute** | the *power calculator* | B–C | `Artifact` + `Evidence` | `math-formalizer`, `numerical-runner`, `dataset-fitter` | Formalize, Execute |
| **II · Verify** | machine-checked *truth* | A | `Validation` (+ proof `Artifact`) | `proof-checker`, `statistical-validator`, `contradiction-checker` | Execute, Validate |
| **III · Retrieve** | the *encyclopedia* | cited (ext.) | `Evidence` (URI + hash + retrieval ts + citation) | `literature-search`, `prior-art-lookup`, `constraint-extractor` | Hypothesize, Design |
| **IV · Visualize** | *seeing the thinking* | n/a (renders the above) | `Artifact` (plot/notebook) + a UI over `tool_invocations` | — (new) | cross-cutting |

A cross-cutting **execution substrate** (§6) underlies Families I, II, IV wherever
code actually runs.

---

## 4. The four families (the proposed tool list)

License posture matters because OpenTheory is a **hosted commercial backend**.
Copyleft (GPL) obligations trigger on *distribution*, not on running code
server-side, so GPL tools (SageMath, Maxima, LAMMPS) are usable as a backend
*service* — just never statically linked/bundled into a shipped binary. The real
landmines are the **proprietary per-seat** engines (Wolfram, Mathematica, Maple).
Picks below default to BSD/MIT/Apache/LGPL, Python-native where possible.

### Family I — Compute (the power calculator) — Grade A–B

| # | Capability | Build-first pick | License | Integration | Grade | Notes |
|---|---|---|---|---|---|---|
| I.1 | **Symbolic CAS** — solve/simplify/calculus, *create & transform formulas*, symbolic linear algebra | **SymPy** | BSD-3 | native Python lib | B | The symbolic backbone. Exact symbolic results = Grade B (not a general proof). Pin version + canonicalize via `srepr()` for hashing (`simplify()` heuristics drift across versions). Escalate to **SageMath** (GPL, run as a sandboxed subprocess) only for heavy number theory / Gröbner / PARI work. **Avoid Wolfram/Maple** (per-deployment licensing). |
| I.2 | **Numerical** — ODE/PDE (`solve_ivp`), optimization, root-finding, special functions, dense/sparse linear algebra | **SciPy / NumPy** | BSD-3 | native Python lib | C | The workhorse. **Float64 is *not* bit-reproducible** (BLAS backend, SIMD, thread count) → Grade C, mechanically *env-pinned*: record an environment fingerprint + tolerance, never treat the float as an exact hash. Force `OMP_NUM_THREADS=1` when bit-identity is needed. |
| I.3 | **Arbitrary / rigorous precision** | **mpmath** (deterministic) + **gmpy2** (correctly-rounded) → **Arb / `python-flint`** (rigorous intervals) | BSD-3 / LGPL | native Python (C ext) | B | `gmpy2` is correctly-rounded → reproducible across platforms. **Arb is the standout**: every result carries a *proven* error radius (ball arithmetic), so a numeric value carries a machine-checkable bound — exact Grade-B evidence that can *feed* a Grade-A proof (the bridge into Verify, §II.3). |
| I.4 | **Units & dimensional analysis** | **Pint** | BSD-3 | native Python lib | B | Cheap, deterministic guardrail that catches a whole class of physics errors mechanically (dimension mismatch → exception). Pin the unit registry version. `astropy.units` if bundling with constants; `unyt` if array performance dominates. |
| I.5 | **Constants & reference data** | **`scipy.constants`** / **`astropy.constants`** (CODATA-versioned) | BSD-3 | native Python lib | B | CODATA 2022 fundamental constants with value/uncertainty (exact, authoritative). `astropy.constants` lets you import a *named* vintage (`codata2018`/`codata2022`) and freeze it — cite the vintage in the ledger, not just the float. |

> **Vision domains served:** every quantitative thread. Formula creation/algebra
> (Riemann, P-vs-NP toy models), constraint fitting (dark matter/dark energy
> parameter spaces), dimensional sanity (all of physics), high-precision evaluation
> (Riemann zero verification).

### Family II — Verify (machine-checked truth) — Grade A

The strongest result the platform can hold: a **binary, reproducible, independently
re-checkable** verdict. The governing pattern, drawn from how AlphaProof-class
systems work, is **untrusted generator → trusted referee**: the LLM proposes, the
*kernel* decides. The model is never trusted; the proof check is.

| # | Capability | Build-first pick | License | Integration | Notes |
|---|---|---|---|---|---|
| II.1 | **Interactive theorem prover** — machine-checked proofs | **Lean 4 + Mathlib** | Apache-2.0 | subprocess via official `repl` (JSON over stdin) + `lake build` | Standardize here: broadest research-math library (~210k theorems), most permissive license, the de-facto target of all current AI-proving tooling. **Pin `(lean-toolchain, mathlib commit, lake-manifest)`.** Verdict = zero errors AND zero `sorry`/`axiom` cheats. Kernel checking is exact (no floats). `LeanDojo` later for tactic-level interaction. Isabelle/HOL is the secondary option (stronger push-button automation via `sledgehammer`). |
| II.2 | **SMT / SAT solver** — constraint & satisfiability oracle, counterexample finder | **Z3** (+ **cvc5**) | MIT / BSD | native Python lib (`z3-solver`, `cvc5`) | A *sat* model is a concrete, pinnable **disproof**; *unsat* can emit a **proof certificate** a third party re-checks — store the certificate, not just the verdict. Deterministic single-threaded with a fixed `random_seed`; parallel/portfolio modes are not. Always pass (and record) a resource limit — an unbounded query runs forever. |
| II.3 | **Rigorous numerics / computer-assisted proof** | **Arb** (`python-flint`) → Lean/Coq interval tactics | LGPL / Apache | native Python (C ext) → in-prover tactic | Interval/ball arithmetic whose output provably contains the true value — turns a float into a *bounded* claim. The gold standard (CoqInterval, Lean interval tactics) verifies the bound *inside the prover*. This is how a numeric experiment earns Grade A. Precedent: Flyspeck (Kepler), Helfgott (ternary Goldbach). |

> **Vision domains served:** bounded, machine-checkable math *now* — elementary
> number theory, Euclidean geometry, algebraic identities, inequalities, recurrence
> proofs (see §5) — plus any thread that needs a *constraint* checked or a
> *counterexample* found. The Millennium-prize math (Riemann, Navier–Stokes, P-vs-NP)
> is a **long-horizon showcase, not the opening target** — leading with it would make
> the platform look grandiose before the ledger has survived a single real enquiry.

### Family III — Retrieve (the encyclopedia) — Grade A–B

Authoritative, *citeable* facts — not general web search. Every retrieval becomes
an `Evidence` row pinned per `primitives.md` (URI + retrieval timestamp + hash +
citation metadata). The pinning strategy splits by source type:

- **Immutable-id sources** (the ID *is* the pin): arXiv `vN`, DOI, PDB id, CODATA
  release, PDG identifier + edition, OEIS A-number, LMFDB label.
- **Mutable sources** (MUST also pin revision/version + retrieval date + content
  hash): Wikidata revision-id, UniProt entry-version + release, Materials Project
  db-version, SIMBAD/PubChem query date.

| # | Capability | Build-first pick | License | Pinnability | Domain |
|---|---|---|---|---|---|
| III.1 | **Literature & prior-art** (`literature-search`, `prior-art-lookup`) | **Crossref/DOI** + **arXiv** + **OpenAlex** | CC0 / public-domain | strong (DOI, arXiv `vN`, stable OpenAlex IDs) | all |
| III.2 | **Structured factual knowledge** | **Wikidata** (SPARQL) | CC0 | mutable → pin revision-id | all |
| III.3 | **Physics/astro reference** (`constraint-extractor`) | **CODATA** + **PDG** + VizieR/SIMBAD | public-domain / CC-BY | strong (release/edition-versioned) | physics |
| III.4 | **Materials reference** | **Materials Project** (`mp-api`) | CC-BY 4.0 | strong (`mp-xxxx` + db-version) | materials |
| III.5 | **Bio/chem reference** | **RCSB PDB** + UniProt + AlphaFold DB + PubChem | CC0 / CC-BY | strong (stable accessions + versions) | bio |
| III.6 | **Math reference** | **OEIS** + LMFDB | OEIS-EULA / CC-BY-SA | strong (A-number / label) | math |

> **Citation anchor:** every `Evidence` row should carry a **DOI** where one exists
> (resolve via `doi.org` content-negotiation → CSL-JSON/BibTeX directly). **Drift
> detection:** re-fetch → re-canonicalize → re-hash → compare against the pinned
> hash; cheap first pass via the source's `ETag`/`version`/`updated` field.
>
> **Licensing flags — do not treat as *primary* citeable ground truth:**
> Wolfram|Alpha (proprietary + unversioned *computed* output — use as a Family-I
> *calculator*, not a citation), NASA ADS (no-redistribution clause — cite the
> bibcode, never persist the record), DBpedia (viral CC-BY-SA — prefer Wikidata's
> CC0). Note: **OpenAlex requires an API key as of Feb 2026** (the polite-pool was
> retired).

### Family IV — Visualize (seeing the thinking) — renders the above

Two distinct jobs the user named: visualize the **results**, and visualize the
agent's **reasoning/process**.

| # | Capability | Build-first pick | License | Integration | Notes |
|---|---|---|---|---|---|
| IV.1 | **Result charts** | **Vega-Lite** (portable JSON spec) + **Plotly** (rich/3D) + **matplotlib** (frozen static) | BSD / MIT / PSF-BSD | agent emits Vega-Lite JSON → `react-vega`; `fig.to_json()` → `react-plotly.js`; matplotlib → PNG/SVG in S3 | **Vega-Lite is the primary artifact format**: a vendor-neutral JSON spec the agent emits directly with no server-side plotting runtime, content-addressed in S3, re-rendered interactively in the Next.js app. Plotly for rich/statistical/3D. matplotlib when a dependency-free *static* image is the goal. Pin the renderer version next to any stored spec. |
| IV.2 | **Formula rendering** | **KaTeX** | MIT | `react-katex`, SSR-prerendered | Synchronous, deterministic HTML you can pre-render and cache with the artifact — renders agent-produced LaTeX with no flicker. Escalate to **MathJax v4** only where LaTeX coverage / equation cross-refs / accessibility demand it. |
| IV.3 | **Notebooks as re-runnable artifacts** | `.ipynb` + **nbformat** + **papermill** + **nbconvert** | BSD-3 | Python libs | Pipeline: agent emits `.ipynb` → **nbformat** validates → **papermill** runs it headless with injected parameters (output notebook → S3, content-addressed: *this executed notebook is the audit artifact*) → **nbconvert** renders an HTML display copy. `.ipynb` does **not** pin dependencies — capture the environment via §6. Consider **Marimo** (reactive, no hidden state, git-diffable `.py`) where reproducibility is worth leaving the ipynb ecosystem. |
| IV.4 | **The reasoning / provenance DAG** | **React Flow** + **dagre** (→ **d3-dag** for merges; **Cytoscape.js** at scale) | MIT | React | *This is the "see the agent's thinking" surface.* Render the checkpoint/branch/merge DAG and each checkpoint's `tool_invocations` as clickable cards: inputs → tool@version → output hash → grade. React Flow handles render/interaction (bring a layout engine — it ships none); **d3-dag** natively handles multi-parent merge nodes (a git DAG); graduate to canvas-based **Cytoscape.js** beyond ~1k nodes. This makes Family I–III invocations *legible* — the agent's chain of computation and citation becomes a navigable map, which is the whole point of a provenance ledger. |

> **Vision domains served:** all — a parameter-space scan (dark matter), a fitted
> light-curve, a rendered derivation (any formalization), and the derivation trace
> itself become first-class, shareable artifacts on the public project page.

---

## 5. First vertical: Math — a ledger benchmark, not a grand-challenge solver

**Decision (2026-06-29): Math first** — but framed deliberately. The opening goal is
*not* "solve the Riemann Hypothesis / P-vs-NP / Navier–Stokes." Leading with Millennium
problems makes the platform look like it's cosplaying as a grand-challenge solver before
it has shown the **ledger** works. The real first question is the one the product exists
to answer: *can OpenTheory turn an enquiry into claims, evidence, falsified branches, and
validated checkpoints?* Math is the cleanest place to answer it, because the §2.1 grade
ladder is unusually crisp there — deterministic computation **and** machine-checked proof
are both first-class, so a claim can visibly climb **D → C → B → A**.

**Build the cross-domain core, but benchmark it against Math.** Do *not* pick
"domain-agnostic" as the target: a generic research machine that never met a real enquiry
will over-abstract. One concrete domain forces the abstractions to become real, and math
is the lowest-ambiguity one (no units, no measurement error, no competing empirical models
at the start).

**The benchmark is a suite of ~20–40 small, bounded tasks**, not one giant problem — each
exercising the primitives end to end (open a `Thread`; create `Claim`s; attach `Evidence`;
*falsify* a bad claim; *branch* a proof strategy; invoke a tool; distinguish *simulation*
from *proof*; *checkpoint* the validated result):

- **Geometry** — measuring across a corner; rectangle diagonals; triangle angle sum; area-preserving rearrangements.
- **Number theory** — even+even is even; irrationality of √2; infinitely many primes; structure of Pythagorean triples.
- **Algebra** — expansion/factorization identities; simple polynomial constraints; inequalities.
- **Sequences** — discover a recurrence; match an **OEIS** candidate (III.6); prove or disprove it.

### Flagship demo — a theorem *emerging* from claim pressure

Not "prove Pythagoras." A thread *"measuring across a corner"* asks what determines the
straight-line distance after walking one leg, turning 90°, and walking another. The
theorem is the claim left standing after falsified branches and a final proof:

| # | Claim | Evidence (tool · family) | Grade | Outcome |
|---|---|---|---|---|
| 1 | Return distance depends only on the two leg lengths | SymPy geometry over 3-4, 6-8, 5-12 (I.1) | C | supports |
| 2 | It's the *sum* of the legs | 3 then 4 → 5, not 7 (exact arithmetic, I.3) | B | **falsifies** → branch closes |
| 3 | Some relation in the *squared* lengths | 3,4,5 and 6,8,10 scale consistently (I.3) | B | supports |
| 4 | dist² = leg₁² + leg₂² | exact rational arithmetic across cases (I.3) | B | supports, not proven |
| 5 | A rearrangement argument proves it in general | **Lean 4** proof (II.1) + optional Mathlib/OEIS lemma lookup (III) | **A** | **validated** |

Pythagoras' theorem isn't *asserted* — it's the surviving claim after a falsified branch
and a machine-checked proof, every step blamed to a named tool at a pinned version. *That*
is the product demo. (Physics — PDG+CODATA, SciPy, eventually DFT/MD — is the natural
second vertical; bio/chem, GPU-heavy and mostly Grade-C, comes later.)

---

## 6. The execution substrate (cross-cutting prerequisite)

Families I, II, and IV.3 run code; that code must run **safely** (it may be
agent-generated) and **reproducibly**. This is the one piece of net-new
infrastructure.

**Build vs buy — we are already on Firecracker.** The backend runs on **Fly
Machines, which are Firecracker microVMs** — VM-grade isolation we already pay for.
So the lowest-friction path is a **dedicated per-task microVM** (or **Fly Sprites**,
Fly's first-party stateful sandbox, S3-friendly, launched Jan 2026) rather than a
new vendor. Alternatives if we want batteries-included: **E2B** (Firecracker,
Apache-2.0, self-hostable on AWS/GCP) or **Daytona** (AGPL-3.0, fully self-hostable).
Lowest-effort DIY hardening: wrap containers with **gVisor (`runsc`)**. Reserve
**Pyodide/WASM** for *no-I/O pure compute* — it can run client-side on Vercel at
≈zero infra cost (great for a quick SymPy eval in the browser). A bare Jupyter
kernel or a plain container is **not** a sandbox for hostile code — both share the
host kernel.

**The reproducibility envelope** (capture on every run; this *is* the
`tool_invocation` record):

- **Pinned environment** — reference images by `@sha256:<digest>` (not tags);
  hash-locked deps (`uv.lock` / `--require-hashes`); set `PYTHONHASHSEED` and
  `SOURCE_DATE_EPOCH`.
- **Seeds** — one explicit seed per stochastic component (`np.random.default_rng`,
  log the `SeedSequence.entropy`); never global RNG state.
- **Network isolation** — `--network none` (determinism *and* anti-exfiltration).
- **Resource limits** — cgroup v2 `memory.max` / `cpu.max` / `pids.max` + an
  external wall-clock kill.
- **Captured outcome** — stdout/stderr separately, exit code / termination signal
  (OOM vs timeout vs clean), wall + CPU time, peak memory, and a **sha256 of every
  output artifact**.

The content address of a run = `hash(image digest + lockfile + source + seeds +
env)`. Model the whole record on **W3C PROV** (Entity / Activity / Agent +
`wasGeneratedBy` / `used` / `wasDerivedFrom`) — a near-exact fit for the existing
`Checkpoint` / `Contribution` provenance graph.

---

## 7. Data-model implications

What this proposal asks of the schema (all additive to `docs/primitives.md`):

1. **Schema-enforce `tool_invocations`.** Promote the free-form JSON on `Checkpoint`
   to a validated shape: `{ tool, version, inputs_hash, outputs_hash, grade,
   resource_used, env_fingerprint }`. Optionally a first-class `ToolInvocation`
   model so a single checkpoint can carry many.
2. **Add the evidence grade (A/B/C/D)** to `Claim` / `Evidence` / `Artifact`, plus a
   secondary mechanical-reproducibility marker (`bit-verifiable` / `env-pinned` /
   `tolerance-only`) on *computed* results. This is the §2.1 ladder made durable — the
   cheapest, highest-leverage change, and the spine of explainable claim confidence.
3. **Content-address `Artifact`s.** `research-git.md` flags this as *target, not
   current* (commit IDs are UUIDs today). Tool outputs are the forcing function:
   store the sha256 and dedupe on it.
4. **An `ArtifactKind`** enum (`derivation`, `proof`, `plot-spec`, `notebook`,
   `dataset`, `simulation-output`) so the frontend renders each appropriately
   (Family IV).
5. **Evidence pinning fields** — `source_version` / `revision`, `retrieved_at`,
   `content_hash`, and a `pin_kind` (immutable-id vs mutable-source) per §III.

None of this is destructive; it enriches existing rows.

---

## 8. Recommended build order

Sequenced by *leverage ÷ effort*, and — critically — honoring the platform's core
design rule (`primitives.md`): **anything an agent will do, a human should be able
to do first.** So every tool below is built as a **human-invokable action in the
workspace first** (e.g. a "compute" panel that attaches a SymPy result as evidence),
and only later driven by an agent through the *same* API. This means the toolbench
delivers value *before* the autonomous agent loop exists, and de-risks it.

**Phase 1 — The MVP calculator + encyclopedia (exact/deterministic, no sandbox yet).**
Pure-Python, in-process, zero licensing risk:
SymPy (I.1) · mpmath/gmpy2/Arb (I.3) · Pint (I.4) · scipy.constants (I.5) ·
Crossref+arXiv+OpenAlex (III.1) + **OEIS** (III.6, the math anchor). Plus the
**data-model changes** in §7.1–7.2 (schema-enforced `tool_invocations` + the grade
ladder). Delivers: a human can attach a *computed* (Grade B) or *cited* result, fully
blamed — and the **math benchmark suite** (§5) becomes runnable end to end.

**Phase 2 — Verify + visualize (where the Math vertical pays off).**
Lean 4 + Mathlib via `repl` (II.1) — the centerpiece: the math benchmark's Grade-A
proofs — · Z3/cvc5 (II.2) · Vega-Lite + KaTeX rendering (IV.1–IV.2) · the
checkpoint/`tool_invocation` DAG view (IV.4). Requires the **execution substrate**
(§6) for Lean. Delivers: machine-checked results (a claim reaching Grade A) and the
"see the thinking" surface — the platform's real differentiator.

**Phase 3 — Reproducible experiments + heavy compute (Grade B–C).**
Sandboxed SciPy/Monte-Carlo runs (I.2) and notebook artifacts (IV.3) on the microVM
substrate; then the **heavy tier** (PySCF first; later OpenMM/GROMACS/FEniCSx/Quantum
ESPRESSO) as a *separate* GPU/HPC job service with explicit Grade-C labeling. This is
the long-horizon lift; treat MD/PDE/DFT as a compute tier, not in-process tools.

---

## 9. Open decisions (need your call)

1. ~~Which domain vertical first?~~ **RESOLVED (2026-06-29): Math first** — framed as
   bounded, machine-checkable *discovery* (the §5 benchmark suite), **not** Millennium-
   problem solving. Build the cross-domain core but force it through math. Anchor tools:
   Lean+Mathlib, SymPy, exact/rigorous arithmetic (Arb), OEIS (LMFDB later). Physics is
   the second vertical; bio/chem later.
2. **Sandbox: buy or DIY?** Per-task **Fly microVM / Sprites** (reuse what we run) vs
   **E2B/Daytona** (batteries-included) vs **gVisor DIY**. Recommendation: start on
   Fly microVMs; revisit E2B only if the ergonomics bite.
3. **How much to schema-enforce `tool_invocations` now** vs leave JSON until Phase 2.
   Recommendation: do `result_grade` immediately (§7.2), defer the full shape.
4. **Human-first confirmation.** Agree the toolbench ships as human-invokable
   workspace actions first (per the design rule), so it's useful before the agent
   execution surface lands?

## Appendix — License posture summary

Clean for a commercial hosted backend (BSD/MIT/Apache/LGPL, run in-process or as a
service): SymPy, SciPy/NumPy, mpmath, gmpy2, Arb/python-flint, Pint, astropy,
Lean/Mathlib, Z3, cvc5, PySCF, Vega-Lite, Plotly, KaTeX, MathJax, Jupyter stack,
React Flow, Cytoscape.js. GPL — fine as a *separate subprocess/service*, never
bundled: SageMath, Maxima, LAMMPS, Quantum ESPRESSO. Avoid in the production path
(proprietary per-deployment licensing): **Wolfram Engine/Mathematica, Maple**.
Data-license care: NASA ADS (no-redistribution), DBpedia (viral BY-SA), OEIS
(non-CC0 EULA), Wolfram|Alpha (proprietary). Prefer CC0 retrieval sources (Wikidata,
arXiv metadata, OpenAlex, Crossref, RCSB PDB).
