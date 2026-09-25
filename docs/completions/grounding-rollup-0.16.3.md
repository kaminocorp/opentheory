# 0.16.3 — Thread-level grounding rollup

**Goal.** Surface the evidence ladder at thread and project scale — the roadmap example
`"3 claims at B, 1 ungrounded"` — now that per-claim `ClaimGrounding` exists.

**Shape.** Read-model aggregation + two existing endpoints + quiet UI. **No schema, no
migration, no new endpoint.** `compute_grounding` and every matrix cell are untouched.

## What landed

- `GroundingRollup` / `GroundingBucket` on `ThreadSummary` and `ProjectOverview`.
  Buckets omit zeros and keep ladder order (`proven`, `refuted`, `B`, `C`, `D`, `cited`,
  `ungrounded`). `total` is the claim count; an empty thread is `{total: 0, buckets: []}`,
  never `"0 ungrounded"`.
- `compute_rollup` (pure) + `rollup_for_claim_ids` / `rollup_by_thread` (batched). Claims
  with no evidence links contribute `ungrounded` — the empty `ClaimGrounding` headline —
  so the caller must pass those ids in, not drop them.
- `GET /projects/{id}/threads` and `GET /threads/{id}` carry the rollup; overview does too.
  Thread list uses one `grounding_by_claim` for the whole project (no N+1).
- Thread list shows the quiet sentence under stage/status; Overview gets a Grounding bay.
  Letter rungs format as `N claims at B`; named headlines use the same words the claim
  chip already uses.

## Tests

- DB-free: the roadmap example; empty ≠ fake ungrounded; ladder order, not input order;
  zero buckets omitted; settled headlines counted.
- DB-gated: thread list, thread detail, and overview share one shape for two-at-D + one
  ungrounded vs an empty thread. The existing claim-count list test also asserts the
  ungrounded rollup.

## Unverified

- The new DB-gated rollup test skips unless `TEST_DATABASE_URL` points at reachable
  Postgres (same gate as the rest of `test_read_models.py`).
- No pixel-level browser walk of the thread-list line or the Overview bay.
