# Toolbench Catalog — The Buildable Tool List, Sorted by Integration Cost

> **Status — working catalog (2026-06-30).** A concrete, buildable companion to the
> design proposal in `docs/plans/agent-research-tools.md`. That doc argues *why* the
> bench exists and *what each tool is for* (the four families: Compute / Verify /
> Retrieve / Visualize). This doc re-sorts the same tools by the axis that actually
> governs build effort — **integration cost** — and names the libraries, licenses,
> and a recommended starter kit. Scope here is deliberately narrow: the *tools and
> libraries themselves*. Data-model questions (the evidence-grade ladder,
> `tool_invocations` shape, artifact write path) are out of scope for this file.

## The organizing principle

The four families tell you what a tool is *for*. For *building*, the question that
decides whether a tool is a week or a quarter is: **where does it run, and what does
it need to run safely?** That sorts the whole bench into four tiers:

- **Tier 0** — pure-Python, in-process, `pip install`. Runs inside the FastAPI
  process we already deploy. Zero net-new infrastructure.
- **Tier 1** — read-only HTTP clients. Outbound calls + a cache/pin layer. No code
  execution.
- **Tier 2** — subprocess to a heavy non-Python toolchain. Ship the binary; a hostile-
  code sandbox is only needed if it runs *agent-written* input.
- **Tier 3** — heavy scientific compute. A separate GPU/HPC job service. Long-horizon.

License posture matters because OpenTheory is a **hosted commercial backend**.
Copyleft (GPL) triggers on *distribution*, not on running code server-side, so GPL
tools are usable as a backend *service* — never statically bundled. Picks default to
BSD/MIT/Apache/LGPL, Python-native where possible. The real landmines are
proprietary per-seat engines (Wolfram, Mathematica, Maple) — avoided entirely.

---

## Tier 0 — pure-Python, in-process, zero infra

These run *inside the FastAPI process*. No subprocess, no sandbox, no new service.
The first one is wireable immediately: `uv add sympy`.

| Capability | Library | License | What it gives you | Produces |
|---|---|---|---|---|
| **Symbolic CAS** | **SymPy** | BSD-3 | solve / simplify / factor / expand, calculus (∫, d/dx, limits, series), symbolic linear algebra, **exact rational arithmetic** | a derivation (formula in → formula out) |
| **Arbitrary precision** | **mpmath** (ships with SymPy) + **gmpy2** | BSD / LGPL | deterministic high-precision floats; correctly-rounded bignums reproducible across platforms | a high-precision number |
| **Rigorous numerics** | **python-flint** (Arb) | LGPL | interval / ball arithmetic — every result carries a *proven* error radius | a number **with a machine-checkable bound** |
| **Units / dimensions** | **Pint** | BSD-3 | dimensional analysis; unit mismatch → exception | a guardrail (pass / throw) |
| **Reference constants** | **scipy.constants** / **astropy.constants** | BSD-3 | CODATA physical constants with value + uncertainty, pinnable vintage | a cited constant |
| **Numerical workhorse** | **NumPy / SciPy** | BSD-3 | linear algebra, ODE/PDE solvers, optimization, root-finding, special functions | a numerical result |
| **SMT / SAT solver** | **Z3** (`z3-solver`) + **cvc5** | MIT / BSD | constraint solving, satisfiability, **counterexample finding**, unsat → proof certificate | a sat-model (disproof) or unsat-certificate |

> **Z3 is the sleeper.** The proposal files it under "Verify" (the hard tier), but
> `z3-solver` is a native Python wheel — it is, in build terms, Tier 0. That means a
> real *machine-checked* capability (find a counterexample, prove a constraint
> unsatisfiable) can ship in the **first** build, not a later phase. The "verify is
> hard / needs a sandbox" framing is true only for **Lean** (Tier 2).

> **NumPy/SciPy float64 is not bit-reproducible** (BLAS backend, SIMD, thread count).
> That's a *result-fidelity* caveat, not a build-cost one — it still runs in-process.
> Force `OMP_NUM_THREADS=1` when bit-identity is needed.

---

## Tier 1 — read-only HTTP clients (API call + cache/pin layer)

No code execution — outbound HTTP from the backend. The only "infra" is a place to
cache responses and record the pin (URI + retrieved-at + content hash). Buildable
right after Tier 0.

| Capability | Source | License | Notes |
|---|---|---|---|
| **Sequence lookup** (the math anchor) | **OEIS** JSON API | EULA — cite, don't redistribute | give it terms `1,1,2,3,5,8` → A-number + formula. The discovery tool. |
| **Literature / DOI** | **Crossref** + **arXiv** | CC0 / public | metadata → BibTeX / CSL-JSON via DOI content-negotiation; arXiv versioned (`vN`) |
| **Citation graph** | **OpenAlex** | CC0 | ⚠️ requires an API key as of Feb 2026 (polite-pool retired) |
| **Structured facts** | **Wikidata** (SPARQL) | CC0 | mutable source → pin the revision-id |

> **Pinning splits by source type.** Immutable-id sources (the ID *is* the pin):
> arXiv `vN`, DOI, OEIS A-number, CODATA release, PDG edition. Mutable sources must
> also pin revision/version + retrieval date + content hash: Wikidata revision-id,
> etc. Detail in `agent-research-tools.md` §III.

> **Data-license flags — do not treat as *primary* citeable ground truth:**
> Wolfram|Alpha (proprietary, unversioned computed output — use as a calculator, not
> a citation), NASA ADS (no-redistribution — cite the bibcode, never persist),
> DBpedia (viral CC-BY-SA — prefer Wikidata's CC0).

---

## Tier 2 — subprocess to a heavy toolchain

Ship the binary/toolchain. A hostile-code sandbox is needed only when the tool runs
*agent-written* input (Lean proofs are agent-written → sandbox; a constant we pass to
Sage is not).

| Capability | Tool | License | The friction |
|---|---|---|---|
| **Theorem prover** (the centerpiece) | **Lean 4 + Mathlib** | Apache-2.0 | `repl` (JSON over stdin) + `lake build`. ~210k theorems, broadest research-math library, most permissive license, the de-facto AI-proving target. But a **multi-GB Mathlib build** + a pinned `(lean-toolchain, mathlib commit, lake-manifest)`. **This is the tool that forces the execution substrate** (`agent-research-tools.md` §6). Verdict = zero errors AND zero `sorry`/`axiom` cheats. |
| **Heavy number theory** | **SageMath** | GPL | run as a subprocess (never bundle); large install. Only when SymPy can't — Gröbner bases, PARI, heavy algebraic number theory. |

> Isabelle/HOL is the secondary prover option (stronger push-button automation via
> `sledgehammer`); Lean is the standardization pick.

---

## Tier 3 — heavy scientific compute (separate job service, long-horizon)

A *compute tier*, not in-process tools — a separate GPU/HPC job runner with explicit
Grade-C labeling. These belong to the **second/third vertical** (physics, then
bio/chem), not the math opening.

| Domain | Tools | License |
|---|---|---|
| Quantum chemistry | **PySCF** (build-first) | Apache-2.0 |
| Molecular dynamics | OpenMM / GROMACS / LAMMPS | MIT / LGPL / GPL |
| PDE / FEM | FEniCSx | LGPL |
| DFT / materials | Quantum ESPRESSO | GPL |

---

## Visualization (a separate frontend axis — runs in Next, not the backend)

| Job | Library | License | What it does |
|---|---|---|---|
| **Result charts** | **Vega-Lite** (primary) + Plotly + matplotlib | BSD / MIT / PSF-BSD | tool emits a portable JSON spec → `react-vega` renders it; no server-side plotting runtime. Plotly for rich/3D; matplotlib for dependency-free static PNG/SVG. |
| **Formula rendering** | **KaTeX** | MIT | LaTeX → HTML, synchronous, SSR-prerendered and cacheable; no flicker. MathJax v4 only if coverage/a11y demands. |
| **Notebooks** | nbformat + papermill + nbconvert | BSD-3 | `.ipynb` as a re-runnable artifact: validate → run headless → render HTML copy. |
| **"See the thinking"** | React Flow + dagre (→ d3-dag for merges; Cytoscape.js at scale) | MIT | the provenance / derivation DAG — the surface that makes the tool chain legible. |

---

## What needs net-new infrastructure (the one real seam)

The whole left half of the bench — **all of Tier 0 + Tier 1** — needs **zero net-new
infrastructure**: it's `uv add sympy z3-solver pint gmpy2 python-flint` plus some HTTP
clients, all running inside the FastAPI process we already deploy on Fly. The
expensive execution substrate (`agent-research-tools.md` §6 — per-task Firecracker
microVM) is required by exactly **one** tool in the buildable-now set: **Lean**. So
the natural build seam is:

> **everything that fits in-process / read-only HTTP**  ·vs·  **Lean + agent-written code**

That seam is also where the licensing risk and the sandbox cost both land — they
coincide, which is convenient for sequencing.

---

## Recommended starter kit

The smallest set that is genuinely useful, buildable now, and needs no sandbox —
while covering all three working families (compute, verify, retrieve):

```text
SymPy   — symbolic CAS + exact rational arithmetic   (compute, Grade B)
Z3      — SMT/SAT: counterexamples & unsat certs      (verify,  Grade A-ish)
OEIS    — sequence lookup by terms                     (retrieve, cited)
```

That four-capability set (SymPy covers both symbolic derivation *and* exact
arithmetic) already lets a user:

- **compute** a symbolic derivation — `factor`, `solve`, `simplify`;
- **falsify** with exact arithmetic — `3 + 4 → 5, not 7` via SymPy `Rational` (no
  separate `gmpy2` needed yet);
- **machine-check** a constraint or find a counterexample — Z3;
- **look up** a sequence or known result — OEIS.

…which is the entire "measuring across a corner" flagship demo
(`agent-research-tools.md` §5) **except** the final Lean proof — and not one of the
four needs the execution substrate.

The thinnest possible first build is **SymPy alone** (one adapter). The
proves-all-three-families build is **SymPy + Z3 + OEIS**, still with no extra infra.

---

## Open threads (not yet decided)

- **First build width** — SymPy only, vs the SymPy + Z3 + OEIS starter kit.
- **The adapter interface** — the common shape every tool conforms to
  (`inputs → run → outputs`, version-pinned). This interface is the actual reusable
  thing being built; SymPy / Z3 / OEIS should all implement the same one.
- **Lean toolchain hosting** — when Lean lands, how Mathlib is built/cached and which
  sandbox (Fly microVM / Sprites vs E2B vs gVisor) wraps it. Deferred until the
  in-process tools are real.
