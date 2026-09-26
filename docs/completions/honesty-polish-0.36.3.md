# 0.36.3 — Honesty polish (R3 residuals)

**Goal.** Close two leftover copy/prompt lies the 0.36.x assessor loop
left after P0/P1 were treated as closed (R3 P2-12 / P2-13). Off
shipped `0.36.0` on `main`. **No schema, no migration.**

Does **not** claim `0.36.1` / `0.36.2` / `0.37.0` / `0.38.0` — those
PRs were open and unmerged when this landed. This branch is not
stacked on them.

## What changed

- **`BranchCreate` / `ValidationCreate`.** OpenAPI docstrings named
  the local-only actor header as how `actor_id` arrives. Production
  acting actor is the verified Supabase bearer JWT (`0.6.0` /
  `0.7.0`). The header path stays in `api/deps.py` behind
  `auth_dev_header_enabled` (default off) and in tests; it is not
  advertised on the create payloads. `CLAUDE.md` and
  `docs/operations/deploy.md` match that split.
- **Planner prompt.** `_render_claims` printed `status:
  {claim.status.value}`. That column defaults to `proposed` and is
  never written to settlement (`compute_signal` is explicit that it
  does not mutate stored status). The prompt now prints `signal`
  (`none` / `contested` / `validated`) from a caller-supplied
  `compute_signal` map — the same derivation the claim read uses.
  `run_agent_pass` loads that map next to grounding. The open-claim
  *filter* is unchanged.

## What was deliberately not done

- No membership gate on original ledger POSTs (that is #23).
- No change to `_open_claims` / orchestrator status filters.
- No `Claim.status` ORM write on validation.
- No Lean / Z3 parser work.
- `create_checkpoint` remains the only Checkpoint writer.

## Honesty note

The two residuals were *teaching dead API surface*: a header
production rejects unless a local flag is on, and a stored claim
field the read model does not treat as settlement. The live paths
were already JWT and `compute_signal`. This PR aligns the words.
