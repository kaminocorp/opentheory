# 0.45.0 — `source.pin` bibliographic source pin

**Goal.** A claim should be able to cite a real paper or work (Crossref,
arXiv, OpenAlex) through a deterministic instrument, not a model
paraphrase. The `0.18.0` lookups already fetch those catalogs; the
named toolbox verb (`source.pin`) was still a pattern in
`toolbench/pinning.py`. Register that verb on the existing instrument
contract so a human or the live MCP door can pin a source the same way
they run `calc.eval`. Do not invent citations. Do not light
`AGENT_LOOP_ENABLED`. Prefer no schema / no migration. Default CI stays
green without those APIs being reachable.

**Shape.** One async retrieval instrument, registered in the code
catalog, graded off-ladder (`cited`), with a quiet drive form + the
existing literature pin card. It **delegates** to
`crossref.lookup` / `arxiv.lookup` / `openalex.lookup` — no second
HTTP client. **No schema, no migration, no new endpoint.** Sits on
shipped `0.44.0` (`6c440ae`, #37).

## What shipped

| Input | Auto-route | Forced provider |
|---|---|---|
| DOI (`10.…` / `doi:` / doi.org) | Crossref identity | Crossref, or OpenAlex when `provider=openalex` |
| arXiv id (prefer `vN`) | arXiv export API | arXiv only (title → `422`) |
| OpenAlex `W…` id | OpenAlex works API | OpenAlex |
| Bibliographic query | Crossref `query.bibliographic` | Crossref, or OpenAlex search when `provider=openalex` |

Every successful run — match or honest no-match — records a `PinRecord`:
`url` (human citation) + `source_url` (the exact API URL hashed) +
`retrieved_at` + `raw_response_hash`. Title / authors / year ride as
short snippets. The raw body is fingerprinted, never stored wholesale.
`output.provider` names which catalog actually answered.

## Providers that resolve a source

- **Crossref** — DOI identity and bibliographic query. Public REST
  works API. No key. Auto default for free text.
- **arXiv** — versioned / unversioned ids via the export Atom API.
  Identity only; it does not search titles.
- **OpenAlex** — `W…` ids on auto-route. DOI or search when
  `provider=openalex`. Optional `OPENALEX_API_KEY` (request param,
  stripped from `source_url`); demo-pool degrade when absent.

The dedicated `*.lookup` instruments remain. `source.pin` is the
unified door, not a replacement.

## Still out

- An arbitrary user-supplied URL with no Crossref / arXiv / OpenAlex
  identity (`pinning.py` still calls that a later add).
- Semantic Scholar or other catalogs.
- Lighting `AGENT_LOOP_ENABLED`. Fly enablement of the gateway or MCP
  child. A live dsh campaign run.
- Lean REPL / LeanDojo. Perpetual ops dashboard. Browser eyeball pass.

## Honesty

- **Network / 5xx / 401 / 429 → `RetrievalError`.** The instrument did
  not run; the write path mints nothing.
- **HTTP 404 / empty search → `undecided`.** Never a fake paper.
- **`provider=arxiv` on a title → validation error.** Do not guess an
  e-print.
- **Tests never hit the live network.** Fake `Fetcher` / `TextFetcher`
  on the existing `RetrievalClient` (10s timeout). Same pattern as
  `0.9.4` / `0.18.0`.

## Grading

`source.pin` is off-ladder (`None` in every cell), same as
`oeis.search` and the literature lookups. A live pin still raises a
claim to `cited` via `Evidence.source_type` (`crossref` / `arxiv` /
`openalex`); an `undecided` no-match does not. It never appears on a
raise path.

## What did not change

- `create_checkpoint` remains the only Checkpoint writer.
- Append-only guards, membership, live MCP inventory (no new stem —
  `run_instrument` already takes any catalog name).
- `AGENT_LOOP_ENABLED` default `false`. Fly `[env]` still has no
  secrets. The gateway / MCP child is **not** enabled on Fly.
- Funder ≠ contributor ≠ validator. Account ≠ Actor.
- Standalone instrument runs still do not debit (same as humans).
- No Alembic revision.

## Tests

- Routing: DOI / arXiv id / `W…` / bibliographic query; forced
  providers; `provider=arxiv` without an id is rejected.
- Instrument: Crossref / arXiv / OpenAlex matches through injected
  fetchers; empty match is `undecided`; fetch failure raises
  `RetrievalError`; raw body is hashed, not stored.
- Catalog / conformance / grading / execution mode (`async`).
- DB-gated write-path: `source.pin` through `run_instrument` lands
  `pinned_source` + `source_type=crossref` (skips without
  `TEST_DATABASE_URL`).
- Frontend: outcome chrome (`Pinned` / `No match`).

## Verification

- `ruff check .` clean.
- Default pytest (no `TEST_DATABASE_URL`): **825 passed, 246 skipped**.
  +21 vs shipped `0.44.0` (804) — routing, pin, empty-match, fetch
  failure, catalog / grading / async mode. +1 skip (the
  `source.pin` write-path round-trip).
- Frontend `typecheck` / `lint` / `test` / `build`: clean; **57 passed**
  (includes `source.pin` Pinned / No match chrome).
- Ledger suite not run in this environment (`TEST_DATABASE_URL` unset).
  Lean / Mathlib stay off. No live Crossref / arXiv / OpenAlex call.

## Unverified

- A live Crossref / arXiv / OpenAlex call from this environment.
- Pixel-level browser walk of the new drive form (same gap as
  `0.14.0`–`0.18.0`). Typecheck / lint / test / build are the
  frontend gate.
- A live MCP / dsh session that actually pins a paper.
