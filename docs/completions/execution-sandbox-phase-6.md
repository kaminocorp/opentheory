# `0.11.6` — Execution Sandbox Phase 6: Frontend Error Copy + Release Ledger

> **Status — completed (2026-07-03).** Phase 6 of
> `docs/executing/execution-sandbox-0.11.md`. Closes the **`0.11.x` Execution Sandbox** line.
> **What comes next:** `0.12.x` thin agent loop per `docs/plans/roadmap-next-steps.md`.

## What this phase delivered

| Deliverable | State |
|---|---|
| `frontend/src/lib/instrument-run-errors.ts` | Shipped |
| `runInstrument` friendly error mapping in `lib/api.ts` | Shipped |
| `docs/changelog.md` index + sections `0.11.1`–`0.11.6` | Shipped |
| Execution plan status → completed | Shipped |
| `docs/plans/roadmap-next-steps.md` → `0.12.x` next | Shipped |
| Success/result cards | Unchanged |

No backend changes. No schema migration.

## Frontend error mapping

### `instrument-run-errors.ts`

| HTTP | Backend signal | User-facing copy |
|---|---|---|
| `422` | detail contains `resource limits` or `timed out` | *This run exceeded the server time or memory limit — narrow the search space or simplify the expression.* |
| `503` | detail contains `busy` | *The server is running other instrument jobs — try again in a moment.* |
| other | — | Preserves `status: detail` from `request` |

`friendlyInstrumentRunError` parses `Error` messages thrown by `request` (`422: …`) and applies the
mapper. Only `runInstrument` uses this path — other API calls keep raw backend detail.

### `toolbench-panel.tsx`

Unchanged. The run mutation still surfaces `(run.error as Error).message`; Phase 6 improves that
string at the API client boundary so the panel needs no Kamino-specific branching.

## Documentation updates

- **`docs/changelog.md`** — six index entries + sections for `0.11.1` through `0.11.6`.
- **`docs/executing/execution-sandbox-0.11.md`** — status banner marked completed (`0.11.6`).
- **`docs/plans/roadmap-next-steps.md`** — current line `0.11.6`; `0.12.x` agent loop recommended next;
  “where we are” mentions bounded execution.
- **`docs/completions/execution-sandbox-0.11.md`** — umbrella completion summary (this line).

## Manual sign-off (Appendix A)

1. Sign in as a project member; run `calc.eval` `2+2` — succeeds; blame tuple shows `resource_used`.
2. In dev, trigger a resource-limit failure (e.g. `test.sleep` via API with low timeout env, or an
   input that times out) — workspace shows the Kamino resource-limit string, not raw `422: …`.
3. Re-run flagship geometry step — normal path unaffected.

## Verification (run at completion)

```bash
cd frontend && npm run typecheck && npm run lint && npm run build
cd backend && uv run ruff check . && uv run pytest -q
```

## Related docs

- Umbrella: `docs/completions/execution-sandbox-0.11.md`
- Phase 5: `docs/completions/execution-sandbox-phase-5.md`
- Execution plan: `docs/executing/execution-sandbox-0.11.md`