# Falsify & Render Phase 5 — Frontend KaTeX in `Formula` (completion notes)

> **Status:** implemented · **Release slice:** `0.10.5` (frontend half) of
> `docs/executing/falsify-and-render-0.10.md` · **Scope:** frontend only — KaTeX typesetting
> in the single render seam; wires `*_latex` companions from Phase 4 into all instrument result
> cards. **No backend, schema, or migration.**
>
> **What it delivers:** toolbench results read as math — superscripts, fractions, relation symbols —
> while SymPy strings remain the provenance fallback when LaTeX is absent or KaTeX rejects input.

---

## 1. What this phase is (and is deliberately not)

Phase 4 added authoritative `*_latex` fields on the backend. Phase 5 is the **show-layer typesetter**:
one `Formula` component accepts an optional `latex` prop; every `result-view.tsx` call site passes the
matching companion when present.

Not in this phase: drive-form LaTeX preview (explicitly out of scope), standalone `formula.render`
instrument, changelog batch (Phase 6).

## 2. What changed, where, and why

### 2.1 Dependencies

- `katex` + `@types/katex` added to `frontend/package.json`.

### 2.2 `formula.tsx` — the render seam

| Behaviour | Detail |
|---|---|
| Props | `expr` (required SymPy string) + optional `latex` |
| Happy path | `katex.renderToString(latex, { throwOnError: false, output: "html" })` → `dangerouslySetInnerHTML` span inheriting `--text` |
| Fallback | Monospace `<code>` chip with `expr` when `latex` is empty, KaTeX throws, or render fails |
| CSS | `katex/dist/katex.min.css` imported once in this file |

`throwOnError: false` ensures a bad latex string never white-screens the toolbench panel.

### 2.3 `result-view.tsx` — `*_latex` wiring

| Instrument | LaTeX props passed |
|---|---|
| `calc.eval` | `expression_latex`, `value_latex` |
| `expr.compare` | `left_latex`, `right_latex`, `difference_latex` |
| `geometry.coordinate_measure` | `distances_latex[key]`; per-angle `degrees_latex`, `radians_latex` |
| `counterexample.search` | `relation_latex`, `witness_relation_latex` |

Helper `asLatex()` trims and drops empty strings so absent companions fall through cleanly.

Geometry degrees render as typeset value + a separate `°` suffix (LaTeX companion is the numeric part only).

`oeis.search` unchanged — no backend `*_latex` companions in `0.10.x`.

## 3. Judgment calls

### 3.1 KaTeX CSS colocated with the seam

Imported in `formula.tsx` rather than `globals.css` so the dependency is localized to the one component
that needs it; Next.js bundles it with the workspace route chunk.

### 3.2 Degrees suffix outside KaTeX

`degrees_latex` from SymPy is `"90"` not `"90°"` — the UI appends `°` after the rendered span so both
latex and monospace paths show the unit consistently.

### 3.3 `expr.compare` latex from output, not inputs

`left_latex` / `right_latex` live on the run **output** (backend enriches after parse). Call sites read
`output.left_latex` etc., not `inputs.left`.

## 4. Verification

```bash
cd frontend && npm run typecheck && npm run lint && npm run build
# all green — /projects/[projectId] ~139 kB (KaTeX CSS + fonts in chunk)
```

**Manual visual check** (not run here): `expr.compare` on `(a+b)**2` vs `a**2+b**2` shows typeset
difference; refuted `counterexample.search` shows typeset `5 \neq 7` (or `=` per SymPy mapping);
geometry angle shows `\pi/2` in radians companion.

## 5. Next slice

**Phase 6 (`0.10.5` docs half)** — changelog for `0.10.1`–`0.10.5`, flagship walkthrough checklist,
completion notes batch.