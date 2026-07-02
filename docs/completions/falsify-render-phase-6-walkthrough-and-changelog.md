# Falsify & Render Phase 6 — Flagship walkthrough + changelog (completion notes)

> **Status:** implemented · **Release slice:** `0.10.5` (docs half) of
> `docs/executing/falsify-and-render-0.10.md` · **Scope:** documentation + sign-off checklist —
> no application code changes beyond Phases 1–5.
>
> **What it delivers:** `docs/changelog.md` entries for `0.10.1`–`0.10.5`, a manual flagship
> walkthrough script for claims 1–4, and this completion batch closing the `0.10.x` line.

---

## 1. What this phase is (and is deliberately not)

Phase 6 is **narrative proof + release ledger** — the executing plan's acceptance bar is a human
walking claims 1–4 of the *measuring across a corner* thread using only shipped instruments, with
results readable via KaTeX. No automated seed data; the checklist below is the sign-off script.

Not in this phase: Claim 5 (Lean proof → Grade A), demo project seeding, agent loop.

## 2. Changelog

`docs/changelog.md` updated with index rows and full sections for:

| Release | Phase | Summary |
|---|---|---|
| `0.10.5` | 5 + 6 | KaTeX in `Formula`; flagship walkthrough complete |
| `0.10.4` | 4 | Additive `*_latex` companions; hash excludes `_latex` keys |
| `0.10.3` | 3 | Workspace drive/show for `counterexample.search` |
| `0.10.2` | 2 | DB-backed write-path + API round-trip for falsifier |
| `0.10.1` | 1 | `counterexample.search` registered; shared relation helpers |

## 3. Flagship walkthrough checklist (claims 1–4)

Manual workspace script — adjust claim text to taste; **instrument inputs are load-bearing**.

| Step | Claim (summary) | Instrument | Inputs (defaults / flagship) | Expected outcome |
|---|---|---|---|---|
| 1 | Leg lengths determine return distance | `geometry.coordinate_measure` | Points `A=[0,0]`, `B=[3,0]`, `C=[3,4]`; dist `A-C`; angle `A-B-C` | `result` — `dist(A,C)=5`, angle `90°` / `pi/2` (KaTeX) |
| 2 | Return distance **equals sum of legs** | `counterexample.search` | `d == a + b`; `a,b:1–10`, `d:1–15` (or pin `3,4,5` for story witness) | `refuted` — witness e.g. `1==2` or `5==7`; typeset relation |
| 3 | Pythagorean check on these legs | `calc.eval` | `3**2 + 4**2 == 5**2` | `result` — relation holds (typeset) |
| 4 | Squared-distance identity for general legs | `expr.compare` | `(a+b)**2` vs `a**2+b**2` | `refuted` — non-zero difference (typeset); **not** equivalent to step 2's sum claim |

**After step 2:** optionally record a validation or close the branch as dead-end (existing `0.4.x`
flows) — the falsification is the load-bearing outcome.

**Claim 5** (Lean proof) → explicitly **`0.12.x+`** with execution substrate.

Cross-link: `docs/executing/falsify-and-render-0.10.md` Appendix A (unchanged intent; this table
is the Phase 6 sign-off copy).

## 4. Verification matrix (recorded)

```bash
cd backend && uv run ruff check . && uv run pytest -q
# 151 passed, 99 skipped (DB-backed ledger tests skip without TEST_DATABASE_URL)

cd frontend && npm run typecheck && npm run lint && npm run build
# all green
```

**Throwaway Postgres gate** (plan prerequisite — re-run before prod merge if ledger code touched):

```bash
docker run -d --name opentheory-pytest-throwaway \
  -e POSTGRES_USER=opentheory -e POSTGRES_PASSWORD=opentheory \
  -e POSTGRES_DB=opentheory_test -p 54329:5432 postgres:16-alpine
TEST_DATABASE_URL='postgresql+asyncpg://opentheory:opentheory@127.0.0.1:54329/opentheory_test' \
  uv run pytest -q
docker rm -f opentheory-pytest-throwaway
```

## 5. Completion doc index (`0.10.x`)

| Phase | Doc |
|---|---|
| 1 | `falsify-render-phase-1-counterexample-search.md` |
| 2 | `falsify-render-phase-2-write-path-and-api.md` |
| 3 | `falsify-render-phase-3-frontend-surfaces.md` |
| 4 | `falsify-render-phase-4-latex-companions.md` |
| 5 | `falsify-render-phase-5-katex-formula.md` |
| 6 | `falsify-render-phase-6-walkthrough-and-changelog.md` (this file) |

## 6. What comes after `0.10.x`

Per `docs/executing/falsify-and-render-0.10.md`: execution sandbox (`0.11.x`), thin agent loop
(`0.12.x`), Tier 1 retrieval wave, verifier wave (Z3 before Lean).