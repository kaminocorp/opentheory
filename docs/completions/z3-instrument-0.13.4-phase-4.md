# `0.13.4` — Z3 instrument Phase 4 completion notes

> **Completed:** 2026-07-22 · **Plan:** `docs/executing/z3-instrument-0.13.md` Phase 4  
> **Scope:** Docs + line close. **Docs only.**  
> A formal code-review pass was **not** run in this implementation session; self-checks
> (ruff, toolbench unit suite, frontend typecheck/lint) are green. Schedule `/review` or
> `review_completions` before treating the line as prod-hardened.

---

## What we were trying to achieve

Record what `0.13.x` shipped, resolve the catalog's long-standing Z3 open threads, and
point the roadmap at the next priorities — without rewriting frozen historical changelog
entries (corrections are new records).

## What landed

| Doc | Change |
|---|---|
| `docs/changelog.md` | Index + full sections for `0.13.0`, `0.13.1`, `0.13.3`, `0.13.4`. Notes Phase 2 deferred. |
| `docs/plans/roadmap-next-steps.md` | Current line `0.13.x`; Z3 shipped; six instruments; priority order updated; follow-ons listed. |
| `docs/plans/toolbench-catalog.md` | Starter kit includes Z3; open thread resolved (shape = `z3.prove`, certificate = marker + unsat-core). |
| `docs/plans/maths-toolbox.md` | `z3.prove` in §Shipped; verifier exclusion narrowed to Lean + follow-ons. |
| `docs/executing/z3-instrument-0.13.md` | Status banner + phase checkboxes updated (0/1/3/4 done; 2 deferred). |
| `docs/completions/z3-instrument-0.13.{0,1,3,4}-phase-*.md` | This series of completion notes. |

## Open decisions — final resolution (recorded)

| # | Resolution |
|---|---|
| 1 Sorts | `int` + `real` only in v1 |
| 2 Nonlinear | Permitted; honest `undecided` |
| 3 Unsat-core | Included (`used_hypotheses` via `assert_and_track`) |
| 4 Version line | `0.13.x` |

## Deferred (explicit)

- **Phase 2** (`0.13.2`) — DB-gated write-path / API / soft-timeout-under-wall-clock tests.
  Not a production code gap; the instrument already composes through `run_instrument`.
- **Formal code review** — plan item left open for a dedicated review pass.
- **Verifier follow-ons** — `z3.satisfy`, boolean connectives, quantifiers, Lean.

## Self-check summary (implementation session)

```bash
cd backend && uv run ruff check .                                    # clean (on touched modules)
cd backend && uv run pytest tests/toolbench -q                       # 137 passed, 22 skipped
cd frontend && npm run typecheck && npm run lint                     # clean
uv run python -c "import z3; print(z3.get_version_string())"         # 5.0.0
```

## Line summary (`0.13.0`–`0.13.4`)

| Phase | Version | Deliverable |
|---|---|---|
| 0 | `0.13.0` | `z3-solver` + `toolbench_z3_timeout_ms` |
| 1 | `0.13.1` | Translator + `z3.prove` + unit tests |
| 2 | `0.13.2` | *Deferred* (tests-only) |
| 3 | `0.13.3` | Drive form + result cards |
| 4 | `0.13.4` | Docs + roadmap/catalog close |
