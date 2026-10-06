# 0.57.1 — Frontend version-skew hotfix

**Goal.** Keep the `0.57.0` Console from throwing against the
live Fly backend, which is still pre-0.53 (`0022` unapplied, no
Fly deploy). Vercel ships `main`'s frontend independently.
Sits on shipped `0.57.0` (`16bf679`, #53).

**Shape.** Frontend + docs only. No backend, no schema, no
migration, no Fly, no live Supabase.

## What shipped

- `opsSpendByAgent` defaults a missing `spend_by_agent` to `[]`.
  Overview no longer reads `.length` on `undefined`.
- Ops turn / last-turn `actor_*` are optional. Missing fields
  render as unattributed.
- Blame `sponsor` and checkpoint `sponsored_by` are optional.
  Helpers skip a missing sponsor instead of inventing one.
- Crew deployed-agents panel: roster `404` is a quiet line
  ("The agent roster isn't available on this backend yet.").
  No raw error text. No deploy controls in that state.
- Rule in `CLAUDE.md` and `docs/operations/deploy.md`: frontend
  reads of a new backend field or route must tolerate the
  previous backend, because Vercel deploys ahead of Fly.

## Tests

- Pre-0.57 ops payload (no `spend_by_agent`, no `actor_*`):
  `opsSpendByAgent` is `[]`; last-turn / turn actor lines do
  not throw.
- Pre-0.57 blame / checkpoint payloads omit `sponsor` /
  `sponsored_by` and still render.
- Roster `404` is `isRosterUnavailable`; other statuses are not.

## Verification

- Frontend typecheck / lint / test (**73 passed**, +4 vs `0.57.0`) / build clean.
- No backend change; ruff / pytest not re-run for this hotfix.

## Unverified

- Live Overview / Crew against production Fly (the motivating
  crash). This slice is the client guard; it does not deploy
  Fly or apply `0022`.
- Slice F (per-agent cap enforcement) is not started.
