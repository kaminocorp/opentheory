import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";

import { listTags, listThreads } from "./api.ts";
import {
  EMPTY_GROUNDING_ROLLUP,
  emptyOnNotFound,
  isNotFoundError,
  normalizeGroundingRollup,
  normalizeTagList,
  normalizeThreadSummaries,
} from "./safe-reads.ts";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

function mockJson(status: number, body: unknown): void {
  globalThis.fetch = (async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    })) as typeof fetch;
}

describe("isNotFoundError / emptyOnNotFound", () => {
  it("recognizes request() 404 shapes and nothing else", () => {
    assert.equal(isNotFoundError(new Error("404: Not Found")), true);
    assert.equal(isNotFoundError(new Error("Request failed with 404")), true);
    assert.equal(isNotFoundError(new Error("500: boom")), false);
    assert.equal(isNotFoundError("404: Not Found"), false);
  });

  it("returns the empty stand-in only for 404", () => {
    assert.deepEqual(emptyOnNotFound(new Error("404: Not Found"), { items: [], total: 0 }), {
      items: [],
      total: 0,
    });
    assert.throws(() => emptyOnNotFound(new Error("500: boom"), []), /500: boom/);
  });
});

describe("normalizeGroundingRollup", () => {
  it("is always a defined total — the live crash was undefined.total", () => {
    assert.deepEqual(normalizeGroundingRollup(undefined), EMPTY_GROUNDING_ROLLUP);
    assert.deepEqual(normalizeGroundingRollup(null), EMPTY_GROUNDING_ROLLUP);
    assert.deepEqual(normalizeGroundingRollup({}), { buckets: [], total: 0 });
    assert.equal(normalizeGroundingRollup({ buckets: [{ headline: "B", count: 2 }] }).total, 0);
    assert.deepEqual(normalizeGroundingRollup({ buckets: [{ headline: "B", count: 2 }], total: 2 }), {
      buckets: [{ headline: "B", count: 2 }],
      total: 2,
    });
  });
});

describe("normalizeTagList", () => {
  it("accepts a bare array or an { items, total } envelope without reading undefined.total", () => {
    assert.deepEqual(normalizeTagList(undefined), []);
    assert.deepEqual(normalizeTagList({ items: [], total: 0 }), []);
    assert.deepEqual(normalizeTagList({ total: 0 }), []);
    const tag = { id: "t1", name: "v1" };
    assert.deepEqual(normalizeTagList([tag]), [tag]);
    assert.deepEqual(normalizeTagList({ items: [tag], total: 1 }), [tag]);
  });
});

describe("normalizeThreadSummaries", () => {
  it("fills grounding_rollup so a thread row can read .total", () => {
    const rows = normalizeThreadSummaries([
      { id: "th1", title: "Measuring across a corner", claim_count: 0 },
    ]);
    assert.equal(rows[0]?.grounding_rollup.total, 0);
    assert.deepEqual(rows[0]?.grounding_rollup, EMPTY_GROUNDING_ROLLUP);
  });
});

describe("listTags", () => {
  it("treats a 404 as an empty tag list — no throw, no .total read", async () => {
    mockJson(404, { detail: "Not Found" });
    const tags = await listTags("b59b93ce-cd99-458a-b190-c7e0196324f3");
    assert.deepEqual(tags, []);
    assert.equal(tags.length, 0);
  });

  it("normalizes an empty paginated envelope", async () => {
    mockJson(200, { items: [], total: 0 });
    assert.deepEqual(await listTags("proj"), []);
  });

  it("returns a shipped bare array unchanged", async () => {
    const tag = {
      id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
      project_id: "proj",
      checkpoint_id: "cp",
      author_id: null,
      author: null,
      name: "v1",
      kind: "milestone",
      notes: null,
      recording_checkpoint_id: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    mockJson(200, [tag]);
    assert.deepEqual(await listTags("proj"), [tag]);
  });

  it("still surfaces non-404 failures", async () => {
    mockJson(500, { detail: "boom" });
    await assert.rejects(() => listTags("proj"), /500: boom/);
  });
});

describe("listThreads", () => {
  it("lets a thread row from an older backend read .total without crashing", async () => {
    mockJson(200, [
      {
        id: "6adaf8a3-c0f2-4652-bff4-ae0861a175c7",
        title: "Measuring across a corner",
        claim_count: 0,
      },
    ]);
    const threads = await listThreads("b59b93ce-cd99-458a-b190-c7e0196324f3");
    assert.equal(threads[0]?.grounding_rollup.total > 0, false);
    assert.deepEqual(threads[0]?.grounding_rollup, EMPTY_GROUNDING_ROLLUP);
  });
});
