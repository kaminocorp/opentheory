# Maths Toolbox — The Core Math Bench (Agreed Instrument List)

> A small set of **deterministic research instruments that turn claims into
> inspectable artifacts and evidence.** That is the product — not "a wrapper around
> SymPy." Each instrument takes typed inputs, runs deterministically, and returns an
> output the append-only ledger can hold: a derivation, a number, a counterexample, a
> rendered artifact, a pinned source — **always recorded against the instrument that
> derived it.**

> **Status — working spec (2026-06-30).** The *agreed scope* for the first toolbox,
> math-first. Third doc in the toolbench set and the one that fixes the list:
> - `agent-research-tools.md` — *why* the bench exists; the four families
>   (Compute / Verify / Retrieve / Visualize).
> - `toolbench-catalog.md` — the full buildable bench re-sorted by **integration cost**.
> - **this doc** — the **agreed v1 instrument set**, enumerated at *function* granularity.
>
> **Decisions baked in (2026-06-30):**
> - **Scope** = Core math bench. **Discipline** = Math-first.
> - **Record the instrument.** Every result is linked to the instrument that derived it
>   — the `(tool, version, inputs) → output` blame tuple — plus the **assumptions** it was
>   computed under. These are the *only* mandatory per-result records (the irreversible
>   facts). Everything else is derived.
> - **No grades, no stamped result-kind.** Whether a result is exact / approximate /
>   retrieved — and any future A/B/C/D grade — is a *function of which instrument ran*, so
>   it's derivable on demand from the blame tuple, never stamped. See *"What every result
>   records"* below.
> - **Interval arithmetic (Arb) is in** the core (it gives a numeric result a proven bound).
> - The verifier layer (Z3 / Lean) and all physics-specific tools are *deferred*.

## The picture

A mathematician's digital workbench: *write and transform formulas, calculate exactly
and numerically, falsify wrong claims, look up what's known, and see the result.* The
instruments group into six benches plus two cross-cutting concerns:

1. **Express** — parse, normalize, render, and **compare** expressions (equivalence).
2. **Calculate** — a primitive calculator + exact / precision / numeric / interval values.
3. **Symbolic (CAS)** — algebra & calculus on exact expressions.
4. **Falsify & discover** — counterexample search, sampling, sequence lookup, source pinning.
5. **Geometry** — coordinate measurement (the flagship-demo instrument).
6. **See & record** — formula rendering, tables, plots.
- *Cross-cutting:* **assumptions** (travel with the evidence) · **the provenance record**
  (the instrument that derived every result).

A long list of abilities, a short list of libraries — but the *unit* is the instrument
(`namespace.verb(inputs) → outputs`), not the library. SymPy backs most of benches
1–3 and 5; the value we add is the deterministic, **recorded** instrument *around* it.

## The organizing fact: symbolic vs numeric

The great divide of this space — and note it is a property *of the instrument*, so it's
recoverable from the recorded tool, never a label we stamp:

- **Symbolic / exact** — manipulate expressions as exact objects (`∫2x dx = x²`,
  `1/3 + 1/6 = 1/2`). Reproducible and exact.
- **Numeric** — compute with floating-point values (`√2 ≈ 1.41421356`); reproducible but
  *approximate* — the answer carries its own tolerance.
- **Interval** — a numeric value *with a proven enclosure* (`√2 ∈ [1.41421356,
  1.41421357]`); the bound is part of the answer.

A researcher constantly moves between them: try it symbolically; if intractable, fall
back to numeric; tighten to an interval when a bound matters. Every one of these is
equally *trustworthy as a computation* (deterministic) — they differ only in what the
answer **is**, which the recorded instrument already tells you.

---

## Bench 1 — Express (notation + equivalence)

The input/normalize/render layer, plus the single most important ledger operation:
*are two expressions the same thing?* All **SymPy** + **KaTeX**.

| Instrument | What it does | Example |
|---|---|---|
| `expr.parse` | Parse plain-text math → canonical expression | `"x**2 - 1"` → expr |
| `latex.parse` | Parse LaTeX-ish input → canonical expression | `"\frac{a}{b}"` → expr |
| `expr.normalize` | Canonical form for hashing/dedup (`srepr`) | expr → stable serialization |
| `expr.to_latex` | Canonical expression → LaTeX | expr → `"x^{2}-1"` |
| **`expr.compare`** | **Are two expressions equivalent?** via `simplify(left − right)` | `(a+b)² − 2ab` vs `a²+b²` → **equivalent**, witness `0` |

> **`expr.compare` is the workbench's core verb, and it has *three* honest outcomes** —
> `equivalent` (difference reduces to `0`), `not_equivalent` (reduces to a witness), and
> `unknown` (didn't reduce — they *might* still be equal; the CAS couldn't decide).
> `unknown` is not a failure: it is the signal to escalate to a proof (the deferred
> verifier). This three-outcome shape — *ran→result / ran→refuted / couldn't-decide* — is
> the contract every instrument conforms to.

## Bench 2 — Calculate (numbers)

A primitive calculator first (it should not *feel* like a CAS to add `2 + 2`), then the
exactness ladder. **SymPy / mpmath / SciPy / Arb.**

| Instrument | What it does | Example |
|---|---|---|
| `calc.eval` | Primitive calculator: arithmetic, powers, roots, comparisons, exact-equality | `3² + 4² == 5²` → `true`; `2 + 2` → `4` |
| `fraction.reduce` | Exact rational arithmetic, zero rounding | `1/3 + 1/6` → `1/2` |
| `numeric.eval_precision` | Any expression/constant to N digits | π to 100 digits |
| `numeric.roots` | Numerical root-finding (symbolic failed) | `cos x = x` → `0.739085…` |
| `numeric.integrate` | Numerical quadrature | `∫₀¹ e^{−x²} dx` → `0.7468…` |
| `numeric.optimize` | Minimize / maximize a function | `min f(x)` |
| `numeric.linalg` | Numerical linear algebra | solve `Ax = b`; eigenvalues |
| **`interval.eval`** | A value with a **proven** error bound | `√2 ∈ [1.41421356, 1.41421357]` |

> The exact instruments (`calc.eval`, `fraction.reduce`, `numeric.eval_precision`,
> `interval.eval`) are the *falsification engine*: they settle a specific case exactly
> and can **falsify** a universal (`3 + 4 → 5, not 7`). The numeric instruments
> (`numeric.*` root/integrate/optimize/linalg) are the honest fallback — the result
> carries its own tolerance; force `OMP_NUM_THREADS=1` when bit-identity is needed, and
> never treat the float as an exact hash. **Interval is the standout** — numeric *with a
> proven bound* — and is **in v1**.

## Bench 3 — Symbolic (CAS): algebra & calculus

*Create and transform exact formulas.* All **SymPy**.

| Instrument | What it does | Example |
|---|---|---|
| `sympy.simplify` | Reduce to a cleaner form | `sin²x + cos²x` → `1` |
| `sympy.expand` / `sympy.factor` | Multiply out / factor | `x² − 1` → `(x−1)(x+1)` |
| `sympy.substitute` | Plug values/expressions in | `x²` at `x=3` → `9` |
| `sympy.solve` | Solve equations, systems, inequalities | `x² − 5x + 6 = 0` → `{2, 3}` |
| `sympy.diff` | Derivatives, incl. partial | `d/dx x³` → `3x²` |
| `sympy.integrate` | Definite & indefinite integrals | `∫₀^∞ e^{−x} dx` → `1` |
| `sympy.limit` | Limits, incl. one-sided / ∞ | `lim_{x→0} sin x / x` → `1` |
| `sympy.series` | Taylor / power-series expansion | `eˣ` → `1 + x + x²/2 + …` |
| `sympy.sum` | Symbolic Σ, Π | `Σ_{k=1}^n k` → `n(n+1)/2` |
| `sympy.matrix` | Symbolic linear algebra (det, inverse, eigenvalues) | eigenvalues of a parametric matrix |
| `sympy.dsolve` | Differential equations symbolically | `y'' + y = 0` → `C₁ sin x + C₂ cos x` |

> **Number theory and basic geometry come free inside SymPy** (primality, factoring,
> coordinate geometry) — no separate tool needed for the common cases.
> **Pinning:** pin the SymPy version (recorded in the blame tuple) and canonicalize via
> `expr.normalize` (`srepr`) — `simplify()` heuristics drift across versions.

## Bench 4 — Falsify & discover

The OpenTheory-native loop: *try to break a claim*, and *identify what's known*. A cheap
local falsifier (no Z3) + the sequence anchor + the pinning primitive.

| Instrument | What it does | Example |
|---|---|---|
| `sample.grid` | Evaluate a relation over a bounded grid of inputs | tabulate `d` vs `a+b` for small integers |
| **`counterexample.search`** | Cheap grid/random search for an input that breaks a claim | claim `d = a+b`; finds `a=3,b=4,d=5` → `5 ≠ 7` |
| `pattern.find_relation` | Suggest a relation that fits sampled rows | rows of `(a,b,d)` → `d² = a²+b²` |
| `oeis.search` | Identify a sequence by its terms | `1,1,2,3,5,8` → Fibonacci (A000045) |
| **`source.pin`** | Pin any external retrieval into a citable record | provider + terms → url, retrieved_at, terms, formula, license_note, `raw_response_hash` |

> **A counterexample is asymmetrically strong.** *Finding* one **definitively falsifies**
> a universal — among the strongest cheap results on the bench. *Not* finding one after
> N samples is *weak* support (absence of evidence ≠ proof) — so the record always keeps
> the search space + N, and "none found" must never render as "proven."
>
> **`source.pin` makes retrieval evidence solid, not flimsy.** OEIS's A-number is the
> pin, but the recorded artifact carries url + `retrieved_at` + terms + formula snippet +
> `license_note` + `raw_response_hash`. (OEIS: cite, don't redistribute.) `source.pin` is
> the reusable Tier-1 pattern for every future external source.

## Bench 5 — Geometry (the demo instrument)

The flagship thread is *measuring across a corner*, which needs a human-runnable
coordinate measurement — not just generic CAS. **SymPy.geometry.**

| Instrument | What it does | Example |
|---|---|---|
| `geometry.coordinate_measure` | Distances & angles between given points | `A=[0,0], B=[3,0], C=[3,4]` → `dist(A,C)=5`, `angle(A,B,C)=90°` |

## Bench 6 — See & record

How results become inspectable. **Tables are mandatory; plots are optional** — discovery
usually begins as a table, not a chart. **KaTeX / Vega-Lite.**

| Instrument | What it does | Example |
|---|---|---|
| `formula.render` | LaTeX → HTML, synchronous, cacheable | renders any `expr.to_latex` output |
| `table.create` | Build a table artifact from rows | `a \| b \| d` for several triples |
| **`table.derive_column`** | Add a *computed* column (this is compute, not display) | derive `a²+b²` and `d²` columns |
| `table.render` | Display a table | the `a,b,d,a²+b²,d²` grid |
| `plot.function` | Graph `y = f(x)`, 2D, as a Vega-Lite spec | `y = x²` over [−3, 3] |
| `plot.points` | Scatter/line of computed results | fitted curve over data |

> `table.derive_column` is **secretly a compute instrument** — a derived column is
> recorded against the instrument that produced it, same as any other computation, so the
> `25 = 25` that falsifies "d = a+b" is itself blamable. Tables straddle benches 3 and 6.

---

## Cross-cutting 1 — Assumptions (travel with the evidence)

The biggest conceptual gap if omitted, and one of only two things that *must* be captured
at write-time (it can't be reconstructed). A CAS result is often only valid under
assumptions (`x > 0`, `n ∈ ℕ`, `denominator ≠ 0`). For the flagship thread: `a > 0`,
`b > 0`, `d > 0`, `angle = 90°`.

- Every instrument accepts an **assumption set** (SymPy's native assumptions:
  `Symbol('x', positive=True)`), and the result is computed *under* it.
- **Assumptions are recorded *on the Evidence/Artifact*, not just passed to the tool** —
  and surfaced on the evidence card in the UI. Otherwise the ledger holds a misleading
  unconditional claim (e.g. `√(x²) = x` recorded without `x ≥ 0`), which it can never edit
  out (append-only). A choice at invocation, not a property of the tool → must be captured.

## Cross-cutting 2 — What every result records (the provenance spine)

Record only what can't be reconstructed later; derive everything else. Two things qualify,
and they are the whole per-result record:

```
The blame tuple   tool        — the instrument that derived this result
                  version     — its library/source version (for reproduction)
                  inputs      — the exact inputs
                  output      — the result (a numeric answer carries its own tolerance/bound)
Assumptions       the set the result was computed under (cross-cutting 1)
```

**Why nothing else.** Whether a result is *exact / approximate / retrieved* — and any
future A/B/C/D *grade* — is a **function of which instrument ran** (`calc.eval` is always
exact; `numeric.roots` is always approximate; `oeis.search` is always a citation). Since
the instrument is recorded, those classifications are **derivable on demand**, never
stamped. This also keeps the platform honest: a stamped grade would be a *naked score*,
exactly what `primitives.md` forbids ("confidence explainable through evidence and
validation history, **not a naked score**"). We record the irreversible facts (the
instrument + assumptions) and reconstruct judgments from them if and when we need them.

> This is the existing hook, schema-enforced. `Checkpoint.tool_invocations`
> (`research-git.md`) already specifies *"for each tool-agent called: name, version,
> inputs, outputs"* and is carried as free-form JSON today — the blame tuple **is** that
> record. The toolbox promotes it to a validated shape; it is not net-new infrastructure.

---

## How each instrument fits the ledger (unchanged invariant)

These are how an `Actor` (human now, agent later) manufactures a result the append-only
ledger can hold. Every run:

- lands as an **`Artifact`** (derivation, plot spec, table, pinned source) and, when
  pointed at a `Claim`, mints an **`Evidence`** row carrying its assumptions;
- composes with the checkpoint chokepoint (`services/checkpoints.py`) exactly as
  validation and branching already do — it never writes the ledger directly;
- records its `tool_invocations` entry — the blame tuple that links the result to the
  instrument that derived it, the determinism contract that makes it reproducible and
  blamable.

**Human-first holds:** every instrument ships as a **human-invokable workspace action
first** (a panel that attaches a result as evidence), and only later is driven by an agent
through the *same* API.

## What this list deliberately excludes (the agreed boundary)

- **Verifier layer (Z3, Lean)** — *deferred.* `counterexample.search` covers cheap local
  falsification without it. Z3 is a near-free future add (pure-Python wheel, no sandbox);
  **Lean** forces the execution substrate (`agent-research-tools.md` §6) and stays far out.
- **Physics tools** — units & dimensional analysis, constants, statistics, tensors/GR, QM
  → *deferred* (math-first). Units + constants are the cheapest physics re-entry point.
- **Heavy compute** (DFT / MD / PDE / FEM) → *deferred*, a separate GPU/HPC job service.
- **Number theory / combinatorics / geometry as *separate* tools** → *not needed*; SymPy
  covers the common cases inside benches 3 and 5.
- **Grades / result classification as a stored field** → *deferred*; derivable from the
  recorded instrument, so add it later only if a real consumer needs it.

## Open items

- **Completeness** — is anything missing from your mental picture of a mathematician's
  desk that doesn't have an instrument above? (Resolved: interval arithmetic **in**;
  grades & stamped result-kind **out** — derived from the recorded instrument.)

## Next steps (not part of the agreed list yet)

- **Map the UI** — give every instrument two columns: *drive* (input affordance — formula
  field, terms box, point editor) and *show* (render surface — formula card, table,
  counterexample card, plot, citation card). The handful of render surfaces becomes the
  toolbench's frontend component library.
- **Design the adapter interface** — the common `inputs → run → outputs` shape
  (version-pinned; the three-outcome result: ran→result / ran→refuted / couldn't-decide)
  every instrument conforms to. *This interface is the real build object;* `calc.eval` /
  `expr.compare` / `oeis.search` are its first conformance tests.
- **Data-model** — schema-enforce the `tool_invocations` blame tuple + record assumptions
  on `Evidence` / `Artifact`, additive to `docs/primitives.md`. **No grade field, no
  stamped result-kind.**
