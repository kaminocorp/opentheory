# Toolbench Catalog — The Buildable Tool List, Sorted by Integration Cost

> **Status — working catalog (updated 2026-07-22), partially shipped (`0.9.x`–`0.13.x`).** A
> concrete, buildable companion to the design proposal in
> `docs/plans/agent-research-tools.md`. That doc argues *why* the bench exists and *what
> each tool is for* (the four families: Compute / Verify / Retrieve / Visualize). This doc
> re-sorts the same tools by the axis that actually governs build effort — **integration
> cost** — and names the libraries, licenses, and a recommended starter kit.
>
> **Shipped:** Tier 0 SymPy instruments (`calc.eval`, `expr.compare`,
> `geometry.coordinate_measure`, `counterexample.search`) + Tier 0 **`z3.prove`** (`0.13.x`)
> + Tier 1 `oeis.search`; adapter registry, write path, provenance spine, workspace UI,
> KaTeX render, execution sandbox. See `docs/plans/maths-toolbox.md` §Shipped in production.
>
> **Not shipped:** Arb/`interval.eval`, literature pins (Crossref/arXiv/OpenAlex), Lean,
> visualization instruments (Vega-Lite tables/plots), `z3.satisfy` / boolean connectives.

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

The original starter kit argued for SymPy + Z3 + OEIS. **As of `0.13.x` we shipped SymPy
(four instruments) + OEIS + `z3.prove`.** That covers the flagship demo
(`agent-research-tools.md` §5) **claims 1–4** with readable KaTeX *and* a machine-checked
proof path for linear-arithmetic claims. Claim 5 (Lean proof) still needs a heavier
execution substrate.

```text
Shipped (0.9.x–0.13.x):
  SymPy   — calc.eval, expr.compare, geometry.coordinate_measure, counterexample.search
  OEIS    — oeis.search (Tier 1, pinned retrieval)
  Z3      — z3.prove (validity: proof / counter-model / undecided)

Next in-process adds (no Lean infra):
  Arb     — interval.eval (optional 0.10.6+ stretch)
  z3.satisfy / bool connectives / quantifiers — verifier-wave follow-ons
```

**Lean** remains the tool that forces net-new infrastructure beyond the existing sandbox.

---

## Open threads

- **Resolved (`0.13.x`):** Z3 instrument shape = single **`z3.prove`** (validity check;
  `sat` branch doubles as exact counterexample-finding). Certificate = **marker
  (`"unsat"`) + optional unsat-core** of named hypotheses on the result payload;
  `artifact_kind="proof"` (free-form VARCHAR, no migration). Full `solver.proof()` terms
  deliberately out of scope for v1. See `docs/executing/z3-instrument-0.13.md`.
- **Lean toolchain hosting** — when Lean lands, how Mathlib is built/cached and which
  sandbox (Fly microVM / Sprites vs E2B vs gVisor) wraps it. Sandbox policy (`0.11.x`) is
  the prerequisite; Lean still needs a heavier substrate for agent-written proof code.
- **Resolved:** first build width (SymPy + OEIS + flagship instruments);
  adapter interface (`0.9.2`); provenance spine (`0.9.1`); Z3 as Tier-0 verifier (`0.13.x`).
