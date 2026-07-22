# `0.13.0` — Z3 instrument Phase 0 completion notes

> **Completed:** 2026-07-22 · **Plan:** `docs/executing/z3-instrument-0.13.md` Phase 0  
> **Scope:** Dependency, config, honesty-timeout contract. **Backend-only; no schema, no migration, no instrument yet.**

---

## What we were trying to achieve

Land the prerequisites for `z3.prove` without shipping the instrument itself: install `z3-solver`, expose a Z3 soft-timeout setting that stays **strictly below** the subprocess wall-clock (so hard problems degrade to honest `undecided` rather than a sandbox kill that mints nothing), and document the knob.

## What landed

| Change | Where | Why |
|---|---|---|
| `z3-solver==5.0.0.0` | `backend/pyproject.toml` + `uv.lock` | Native MIT wheel; no system solver. Resolved version at install: **5.0.0.0**; in-process `z3.get_version_string()` → **`5.0.0`**. |
| `toolbench_z3_timeout_ms: int = 10_000` | `backend/app/core/config.py` | Soft solver timeout (ms). Comment records the "< wall-clock ⇒ honest undecided" rationale. |
| `TOOLBENCH_Z3_TIMEOUT_MS=10000` | `backend/.env.example` | Documents the knob for local/prod ops. |

## Decisions applied (from plan open threads)

Deferred to Phase 1 for implementation, but Phase 0 assumes the plan's recommendations:

1. **Sorts:** `int` + `real` only in v1.  
2. **Nonlinear:** permitted; honest `undecided` on the undecidable fragment.  
3. **Unsat-core:** include (named hypotheses via `assert_and_track`).  
4. **Version line:** `0.13.x` (not folded into `0.12.x`).

## Review checks (Phase 0)

- [x] Dependency is a wheel (`z3-solver` pure install via `uv`, no apt/brew solver).  
- [x] Default `toolbench_z3_timeout_ms` (10_000) is strictly below `toolbench_wall_timeout_s * 1000` (30_000).  
- [x] Sanity: `uv run python -c "import z3; print(z3.get_version_string())"` → `5.0.0`.  
- [x] Settings load: `settings.toolbench_z3_timeout_ms == 10000`.

## What this phase deliberately did *not* do

- No instrument, registry entry, tests, frontend, or changelog index entry yet (those are Phases 1 / 3 / 4).  
- No migration / schema change (none needed for the whole `0.13.x` line).

## Commands run

```bash
cd backend && uv add z3-solver
uv run python -c "import z3; print(z3.get_version_string())"   # 5.0.0
uv run python -c "from app.core.config import settings; ..."     # default < wall-clock
```
