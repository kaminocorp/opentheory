# 0.28.0 — Live OpenRouter price metering

**Goal.** Budget is real accounting. A flat blended
`agent_token_rate_usd_per_1k` drifts from what OpenRouter actually bills.
Agent passes should debit `ComputeDebit` at the model's live prompt /
completion rates when the price API is available, and fall back honestly
when it is not.

**Shape.** Cached, short-timeout catalog fetch + snapshot columns on the
existing append-only debit. Migration `0020_compute_debit_live_rates`
(additive). No new HTTP endpoint. The agent remains a contributor — never
a funder, never a validator. Rebased after shipped `0.27.0` concurrent
sub-passes (`0019_concurrent_subpasses`). Does not claim that version.

## What shipped

- `app/agent/pricing.py` — `GET /models` client (`OpenRouterPriceClient`),
  in-process TTL cache, `quote_model_price` (never raises; always returns
  a quote), `usage_to_cost` (split billing or fallback).
- `record_compute_debit` resolves a quote (or accepts one from
  `run_agent_pass`) and snapshots `rate_source`, the live split rates, and
  prompt/completion token counts when known.
- `run_agent_pass` fetches the quote **before** planning (same snapshot for
  `ProjectBudgetPolicy` and the debit) so a slow catalog cannot sit on the
  far side of an LLM call. Timeout default 2s.
- Settings / env: `OPENROUTER_LIVE_PRICES` (default true),
  `OPENROUTER_PRICE_CACHE_TTL_S` (3600), `OPENROUTER_PRICE_TIMEOUT_S` (2).
  Same `OPENROUTER_API_KEY` as completions — no second key, no second
  dark-launch flag.
- Fallback reasons recorded on `notes`: `openrouter_api_key_missing`,
  `openrouter_price_timeout`, `openrouter_price_fetch_failed`,
  `model_not_in_openrouter_catalog`, `live_prices_disabled`,
  `openrouter_price_catalog_empty`.
- Tests disable live prices in `conftest.py` so a local `.env` key cannot
  reach the network. Live-path tests re-enable the flag and inject
  `httpx.MockTransport`.

## Billing rules

| Situation | Amount | `rate_source` |
|---|---|---|
| Live catalog + prompt/completion split | prompt × prompt rate + completion × completion rate; leftover total (reasoning) at completion rate | `openrouter_live` |
| Live catalog + total tokens only | total × mean(prompt, completion) | `openrouter_live` |
| Stale cache, refresh failed | same as live | `openrouter_live` (notes say stale) |
| Missing key / timeout / fetch fail / unknown model / live off | `rate_for_model` (catalog `usd_per_1k` else settings default) | `catalog_override` or `blended_fallback` |

Tokens that moved are always billed. A true $0 live price still writes the
row so the snapshot is auditable. A failed price fetch never skips the
debit.

## What did not change

- One debit per pass (partial unique on `agent_run_id`). Replan tokens
  update the trace but do not add a second row — existing `0.19.0` /
  `0.20.0` shape.
- Funder ≠ contributor ≠ validator. No `FundingAllocation`, no `fund`
  contribution, no auto-validate, no auto-merge.
- Per-pass safety caps. Dark-launch `AGENT_LOOP_ENABLED`.
- Frontend budget numbers still sum `ComputeDebit.amount`.

## Tests

- DB-free: catalog parse; split / unknown-split / remainder / fallback
  math; live quote; missing key; live-prices-off; timeout; fetch failure;
  unknown model; cache hit; TTL refetch; stale-cache-on-refresh-failure;
  catalog override on fallback; migration `0020` revision linkage
  (`down_revision = 0019_concurrent_subpasses`), single-head,
  model/migration column agreement, enum labels; LLM client parses
  `prompt_tokens` / `completion_tokens`.
- DB-gated (skips without `TEST_DATABASE_URL`): existing `0.19.0` /
  `0.27.0` metering still holds; the fallback path records `rate_source =
  blended_fallback` and a `rate fallback:` note (conftest keeps live
  prices off). Reservation envelopes use the same quote as the debit.

## Unverified

- No live agent pass against OpenRouter. The loop is still dark in
  production until the ops flip.
- No pixel-level browser walk (budget numbers are the same read model).
- Replan tokens after the first planning call are still not added to the
  debit (append-only, one row per pass).
- Concurrent first-pass race on `available` is addressed by `0.27.0`
  reservation holds; this line uses the same live/fallback quote for the
  envelope and the debit.
- Rebased onto shipped `0.27.0` (`0019_concurrent_subpasses`); this
  release is `0020`.

## Ops

See `docs/operations/deploy.md` § Live OpenRouter price metering.
`OPENROUTER_LIVE_PRICES=false` is the kill switch if `/models` is
unhealthy; metering continues at the blended rate.
