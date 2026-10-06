# 0.49.1 — Perpetual ops Overview eyeball pass

**Goal.** Close the leftover `0.49.0` verification: actually run the
backend and frontend locally, open a project's Overview in a real
browser, and confirm the quiet Perpetual ops bay renders honestly
across the states it claims to handle. Do not light
`AGENT_LOOP_ENABLED`. Do not enable the gateway or MCP child on Fly.
No campaign. No schema.

**Shape.** Local FastAPI + Next against a throwaway Postgres 16.
Projects and funding went through the public HTTP writers. Harness
spend used `record_compute_debit`. Remaining-room holds used
`write_daily_cap_adjustment`. One pot-exhausted row used the
`test_ops_ledger._add_debit` fixture shape (`$1.00` / 200 tokens) so
pot-exhausted is not also daily-cap exhausted. **No schema, no
migration.** Sits on shipped `0.49.0` (`ba7055b`, #42).

## Why this slice

PR #42 listed a pixel-level browser walk of the Overview bay as
unverified. API tests cannot see currency rounding, tab contract, or
narrow wrap. This slice is that walk.

## What was verified (Chrome, desktop 1280 and narrow 390)

| State | What the bay showed |
| --- | --- |
| Unfunded (`funded == 0`) | Pill **Unfunded**, not Exhausted. Funded / spent / reserved / available `$0.00`. Holds empty. Recent rows empty. Cap **Room**, `0 / 20,000`. |
| Funded, budget remaining | Pill **Available**. Funded `$25.00`. Spent `$0.0004`. Available `$24.9996`. Cap **Room**, `80 / 20,000 · 19,920 remaining`. |
| Funded-and-exhausted pot | Pill **Exhausted**, not Unfunded. Note: unfunded is a different state. Funded `$1.00`, available `$0.00`. Daily cap still **Room** (`200 / 20,000`). |
| Holds + recent rows | Paired `hold_id` Released (500 tok). Open identified hold (1,200 tok). Legacy id-less Open with `unknown hold_id` and the Pre-0.48.0 leftover note (75 tok). Newest **20** harness rows, not more. |
| Refusals | Same honesty block on every loaded bay: a refused start writes nothing; the ledger cannot list refusals. No invented log. |
| Gateway / MCP-on-Fly | Pills **Gateway unknown** and **MCP child unknown**. Built-in loop **dark**. |
| Invalid `OPENTHEORY_HARNESS_DAILY_TOKEN_CAP` | Restarted this API process with `not-a-number`. Pill **Cap unknown**. Line `Used 0 today · cap unknown`. No guessed 20,000 remaining. Child override still labeled unknown. |
| Child-only override | Always in the cap note: this process's cap/TTL is what it sees; a campaign-child override is unknown here. Stay-dark: the child was not started. |
| Missing project | `GET /projects/{id}/ops` → `404 Project not found`. Overview of a missing id shows **Project unavailable** (the workspace 404s before the ops bay mounts). |
| Tab contract | Exactly five in-page tabs: Research, Instruments, Crew, Funding, Overview. CommandRail is Projects + those five. No sixth tab. |
| Narrow 390 | Pot metrics wrap 2×2. Pills wrap. Holds and the 20-row list stay readable. No horizontal blowout. |

Open holds older than `OPENTHEORY_HARNESS_HOLD_TTL_SECONDS` (300)
correctly flip to **Open (stale)** — that is the TTL clock, not a
guess.

Nothing on the page estimated a number. Ledger sums and process
settings only.

Screenshots (agent artifacts):

- `01-unfunded-desktop.png`
- `02-funded-remaining-desktop.png`
- `03-pot-exhausted-desktop.png`
- `04-holds-turns-desktop-top.png` / `04-holds-turns-desktop-bottom.png`
- `05-missing-project-desktop.png`
- `06-tab-contract-desktop.png`
- `07-holds-turns-narrow-top.png` / `07-holds-turns-narrow-bottom.png`
- `08-unfunded-narrow.png` (header + five-tab strip at 390)
- `09-invalid-cap-desktop.png`
- `10-unfunded-narrow-ops.png` (ops bay at 390)

## Bug closed

Default `Intl` currency rounding (2 dp) turned Numeric(12, 6) ledger
dust into an invented zero (`$0.000400` → `$0.00`, `$24.999600` →
`$25.00`) on the Perpetual ops pot and the Overview budget grid.
`formatOpsMoney` now keeps up to 6 fraction digits. One honesty test.

## What did not change

- `create_checkpoint` remains the only Checkpoint writer.
- `AGENT_LOOP_ENABLED` default `false`. Fly `[env]` untouched.
- FastAPI still does not import `app.harness`.
- No Alembic revision. No campaign started. No sixth tab.

## Honest caveats

- A live OpenRouter / `dsh` session was not run.
- Fly enablement of the harness child was not run (stay dark).
- The child-only cap override was verified as the labeled unknown,
  not by starting a campaign child.
- Missing-project Overview is a workspace 404, not the ops bay's
  "Could not load ops" — the bay never mounts without a project.

## Tests

- Frontend: **63** node:test cases (+1 money-precision honesty).
- Existing ops API / ledger / import-posture tests unchanged.
