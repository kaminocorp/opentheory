# 0.18.0 — Tier-1 literature pin instruments

**Goal.** Widen what an agent pass (or a human) can retrieve: pin a Crossref DOI, a versioned
arXiv e-print, and an OpenAlex work as content-addressed Evidence through the same
`source.pin` shape `oeis.search` proved — landing an attributed checkpoint through
`run_instrument`, never minting on a failed fetch, never faking a paper on an empty match.

**Shape.** Three new async retrieval instruments, registered in the code catalog, graded
off-ladder (`cited`), with drive forms + pin cards in the toolbench. **No schema, no
migration, no new endpoint.**

## What shipped

| Instrument | Locator | Source | Pin identifier |
|---|---|---|---|
| `crossref.lookup` | DOI or bibliographic query | Crossref REST `works` | DOI |
| `arxiv.lookup` | arXiv id (prefer `vN`) | arXiv export API (Atom) | versioned arXiv id |
| `openalex.lookup` | DOI, `W…` id, or search | OpenAlex works API | OpenAlex work id |

Every successful run — match or honest no-match — records a `PinRecord`: `url` (human
citation) + `source_url` (the exact API URL hashed) + `retrieved_at` + `raw_response_hash`.
Title / authors / year / container ride as short snippets on `name` / `formula`. The raw
body is fingerprinted, never stored wholesale.

## Honesty

- **Network / 5xx / 401 / 429 → `RetrievalError`.** The instrument did not run; the write
  path mints nothing.
- **HTTP 404 → successful empty match.** The source said nothing is here; status is
  `undecided`, the pin still cites the lookup that was run.
- **Bibliographic / search hits** report `match_count`. A top hit is pinned only when it
  carries a real identifier (DOI / OpenAlex id). Zero hits → `undecided`.
- **Tests never hit the live network.** `httpx.MockTransport` and injected `Fetcher` /
  `TextFetcher` fakes.

## OpenAlex key posture

OpenAlex retired the polite-pool `mailto` on 2026-02-13. A free API key is the real quota;
the unauthenticated demo pool still answers a handful of calls.

`OPENALEX_API_KEY` is **optional**. The process boots without it. When set, the key is a
request param and is stripped from the recorded `source_url` so a secret never lands on
the ledger. When absent, the instrument uses the public demo pool — documented as
fine for a human lookup, not for an agent loop. Tests inject a fetcher and never need a
key.

`TOOLBENCH_RETRIEVAL_MAILTO` is a separate, non-secret contact address embedded in the
outbound User-Agent (Crossref polite pool; courtesy on arXiv / OpenAlex).

## Grading

All three rows in `app/toolbench/grading.py` are off-ladder (`None` in every cell), same
as `oeis.search`. A live pin still raises a claim to `cited` via `Evidence.source_type`
(`crossref` / `arxiv` / `openalex`); an `undecided` no-match does not.

## Unverified

- DB-gated write-path tests in `test_instruments_write_path.py` skip without
  `TEST_DATABASE_URL`. They are written (Crossref / arXiv / OpenAlex through
  `run_instrument`) and should be run the next time a test database is available.
  The default suite was **369 passed, 131 skipped**.
- No pixel-level browser walk of the new drive forms / pin cards (same gap as
  `0.14.0`–`0.16.0`). Typecheck / lint / build are the frontend gate.
