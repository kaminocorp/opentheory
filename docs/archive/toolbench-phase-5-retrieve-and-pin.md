# Toolbench Phase 5 — Retrieve + Pin (OEIS, Tier 1) (completion notes)

> **Status:** implemented · **Release slice:** `0.9.4` (Phase 5 of
> `docs/executing/toolbench-provenance-and-first-instruments.md`) · **Scope:** backend — the first
> *retrieval* instrument + the reusable pinning primitive + the outbound HTTP/cache layer. **No HTTP
> route yet** (Phase 6), **no frontend** (Phase 7). No migration.
>
> **What it delivers:** `oeis.search` — identify an integer sequence by its terms via the OEIS search
> API — landing in the ledger as **solid, cited retrieval evidence**: a pinned record carrying `url`
> + `retrieved_at` + `raw_response_hash`, not a flimsy quote. Look up Fibonacci by `1,1,2,3,5,8` and
> the ledger holds an `A000045` pin. This is the first instrument whose output is **not** a pure
> function of its inputs, which forced three small, principled extensions to the Phase-2/3 contract.

---

## 1. What this phase is

Phase 4 gave three pure, synchronous compute instruments. Phase 5 adds the *retrieval* family: an
instrument that reaches an external, mutable source and stamps a real-time `retrieved_at`. The plan
names the consequence directly — its determinism contract shifts from "re-running returns identical
bytes" to **"the pinned record reproduces what was retrieved."** The value is the same as everywhere
on the bench: not the call to OEIS, but the *recorded, reproducible, cited* instrument around it.

`uv add httpx` (`>=0.28.1`) promotes httpx to a production dependency (it was dev-only for the test
client).

## 2. The contract extensions (the load-bearing design)

A retrieval instrument breaks an assumption Phases 1–4 baked in: that `run` is a pure, synchronous
function of its inputs. Three minimal, backward-compatible extensions resolve it — every existing
compute instrument is untouched by them.

- **`Instrument.run` may be async** (`adapter.py`). Its return type widens to
  `InstrumentResult | Awaitable[InstrumentResult]`. A retrieval instrument implements `run` as
  `async def` (it awaits the network); compute instruments stay synchronous. This keeps *one* `run`
  verb rather than a second "fetch" method with a divergent signature.
- **The write path awaits when needed** (`services/tool_runs.py`). One added line —
  `if isawaitable(result): result = await result` — inside the existing `try`, still **before any
  `db.add`**. So a retrieval failure (network / non-2xx → `RetrievalError`) follows the *same*
  failure split as a compute exception: the instrument did not run → mint nothing → 4xx. The
  hermetic DB-free failure tests still hold (the raise happens before the session is touched).
- **`InstrumentResult.source_type`** (`adapter.py`) — an optional provenance hint so a retrieval
  instrument marks the `Evidence` it produces as externally sourced (`"oeis"`) rather than the
  default `"tool"`. The write path uses `result.source_type or "tool"`. It is a *where-it-came-from*
  hint, **not** a new credit axis (funding ≠ contribution ≠ validation is untouched).
- **Conformance is async-aware** (`conformance.py`) — the behavioural check can't await without an
  event loop (and shouldn't do network I/O), so for an async `run` it is *structural-only* and
  closes the un-awaited coroutine cleanly. The async instrument's output is verified in a dedicated
  async test instead. The structural auto-coverage test covers `oeis.search` unchanged.

## 3. What changed, where, and why

### 3.1 `app/toolbench/retrieval.py` (new) — the HTTP + cache layer

`RetrievalClient.get_json(url) -> Retrieval` (async): fetches, decodes JSON, and returns a frozen
`Retrieval(url, retrieved_at, raw_response, parsed)`. A `transport` injection seam lets tests drive
the **real** parse/hash/cache path with an `httpx.MockTransport` and canned bytes — **no live network
in CI**. A small LRU-ish cache keyed by URL bounds re-fetches; a cache hit returns the *earlier*
`Retrieval` verbatim (including its original `retrieved_at`), which is exactly the determinism
contract — the pin reproduces what was retrieved. Any fetch/parse failure becomes one
`RetrievalError`.

### 3.2 `app/toolbench/pinning.py` (new) — the `source.pin` pattern

`build_pin_record(...) -> PinRecord`: assembles the citable record — `provider`, `identifier` (the
pin), `url`, `retrieved_at` (ISO-8601), `terms`, short `name`/`formula` snippets, `license_note`, and
`raw_response_hash` (sha256 of the exact response). The hash is the honesty anchor: it **proves what
was retrieved without redistributing it** — OEIS's licence is *cite, don't redistribute*, so we store
the pin, never a bulk copy. This is a **primitive, not a registry instrument** (§4.1), reused by
`oeis.search` and every future external source.

### 3.3 `app/toolbench/instruments/oeis_search.py` (new) — `oeis.search`

An `async` retrieval instrument: builds the OEIS `search?q=…&fmt=json` URL from the terms, fetches via
its injected `Fetcher` (a `RetrievalClient` in production), parses the top result's `number` into an
A-number (`45 → "A000045"`), and wraps everything in a `PinRecord`. Outcomes: a match → `result`
(kind `pinned_source`, `source_type="oeis"`); a clean no-match (`results: null`) → `undecided`
(escalate — never a false "no such sequence" claim); a failed fetch propagates `RetrievalError` (→
did not run). `engine="oeis"`, `engine_version="search-api"` (§4.2).

### 3.4 Registration + the Phase-2 assertion

`instruments/__init__.py` registers `OEIS_SEARCH` (now four production instruments).
`test_conformance.py`'s registry assertion is broadened to include `oeis.search`; the structural
auto-coverage parametrization picks it up automatically.

## 4. Judgment calls

### 4.1 `source.pin` is a reusable primitive, not (yet) a registry instrument

The plan lists `source.pin` in the Bench-4 instrument table, but its natural input is *a provider
response*, which is awkward as a catalog instrument a human drives directly. I implemented it as the
`build_pin_record` primitive that `oeis.search` (and future retrieval instruments) compose with — the
"reusable Tier-1 pattern" the plan emphasises. A standalone `source.pin` **instrument** that pins an
arbitrary user-supplied URL is a clean later add (it would reuse this exact primitive).

### 4.2 `engine_version` for OEIS is an API-surface label, not a library version

OEIS is a live, unversioned service. For a retrieval instrument the reproduction anchor is the **pin**
(`retrieved_at` + `raw_response_hash`) recorded in the output, not `engine_version`. So
`engine_version="search-api"` labels the queried surface; conformance only requires it be a non-empty
string. Documented so a reviewer doesn't read it as a pinned dependency.

### 4.3 A clean "no match" is `undecided`, not `refuted` or `result`

Finding no OEIS entry does not *falsify* anything (not `refuted`) and is not a positive identification
(not `result`). It is a successful retrieval that could not decide → `undecided` (the escalate seam) —
and it **still** mints a citable pin (the negative retrieval is itself recordable). Only a *failed
fetch* mints nothing.

### 4.4 Pin fields ride in `evidence_metadata`/output, `source_type` set to the provider — no schema change

Phase 5 adds **no migration**. The pin fields land in the run output (hence the artifact metadata,
the evidence metadata, and the blame tuple); the one first-class signal is `Evidence.source_type =
"oeis"` (an existing column, via the new `InstrumentResult.source_type`). Surfacing pin fields as
dedicated Evidence columns is deferred until a consumer needs to query them — consistent with the
spine's "record the irreversible facts, derive the rest".

### 4.5 The cache reflects the determinism contract (a hit returns the earlier retrieval)

A cached query returns the original `Retrieval` with its original `retrieved_at`. That is deliberate:
the guarantee is "reproduces what was retrieved," not "re-fetches now." A future cache-bypass /
freshness policy is a later concern; the plan asks only for a small in-process cache, which this is.

## 5. Verification

| Check | Result |
|---|---|
| `uv run ruff check .` | **clean** |
| `uv run pytest tests/toolbench` | **49 passed / 9 skipped** |
| `uv run pytest` (full suite) | **113 passed / 89 skipped** (+11 passed over Phase 4's 102) |
| `from app.main import create_app` | imports clean with httpx/retrieval in the graph |
| catalog serialization | all four descriptors emit JSON Schema (incl. the nested `PinRecord`) and are JSON-serializable (Phase-6-ready) |

**DB-free tests (run in the default suite — the real retrieval verification, no network):**

- **pinning** — `raw_response_hash` is a stable sha256; `build_pin_record` captures identifier /
  ISO `retrieved_at` / the hash (not the bytes) / terms.
- **retrieval client** (via `httpx.MockTransport`) — parses + exposes the exact bytes; **caches by
  URL** (one round-trip for a repeat query, same object returned); a non-2xx raises `RetrievalError`.
- **`oeis.search`** (via a fake fetcher) — identifies + pins Fibonacci (`A000045`, cites the sequence
  page, `raw_response_hash` present, `source_type="oeis"`, **the raw body is not stored**); a clean
  no-match → `undecided` with a still-citable pin; a fetch failure propagates `RetrievalError`;
  `<3` terms rejected; structural conformance holds.

### Not run here (honest gap)

Per the no-local-DB / verify-against-live policy, the **1 DB-backed write-path test**
(`test_oeis_search_lands_a_pinned_external_evidence`) — the async retrieval composing through the
chokepoint into a `pinned_source` artifact + an `oeis`-sourced `Evidence` + the pin in the blame
tuple — **skips** without `TEST_DATABASE_URL` (joining Phase 3's 5 + Phase 4's 3 = **9** skipped
DB-backed toolbench tests). The async write-path is structurally identical to the sync one it extends
by a single `await`; the end-to-end atomic commit is exercised only in that DB-backed set. Pending a
throwaway Postgres or CI.

## 6. Scope boundary

No `GET /instruments` or `POST …/run` route (Phase 6). No frontend (Phase 7). No live OEIS call in
tests (mocked throughout). No standalone `source.pin` registry instrument yet (§4.1). No Z3/Lean, no
`numeric.*`/`interval.*`, no object-storage artifact path.

## 7. Next step — Phase 6

The human-invokable API surface: `GET /instruments` (the Phase-2 catalog, root-mounted, public) and
`POST /projects/{id}/instruments/{name}/run` (declares `ActingActor`, gated to project membership,
resolves the instrument from the registry — owning the 404-on-unknown-name — and calls
`run_instrument`). That is the slice that makes Phases 4–5 usable from the product and demoable:
`curl` the catalog, run `calc.eval` or `oeis.search` as a signed-in member, and see the checkpoint
appear in the ledger.

**Release/deploy follow-ups** (not done here, matching Phases 1–4): the `0.9.4` entry in
`docs/changelog.md` and `fly deploy` belong to the release step, once the DB-backed write-path
verification is greenlit.
