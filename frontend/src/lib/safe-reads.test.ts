import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  EMPTY_GROUNDING_ROLLUP,
  emptyOnNotFound,
  isNotFoundError,
  normalizeGroundingRollup,
  normalizeTagList,
  normalizeThreadSummaries,
  readTagList,
  readThreadSummaries,
} from "./safe-reads.ts";

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

describe("readTagList (listTags contract)", () => {
  it("treats a 404 as an empty tag list — no throw, no .total read", async () => {
    const tags = await readTagList(async () => {
      throw new Error("404: Not Found");
    });
    assert.deepEqual(tags, []);
    assert.equal(tags.length, 0);
  });

  it("normalizes an empty paginated envelope", async () => {
    assert.deepEqual(await readTagList(async () => ({ items: [], total: 0 })), []);
  });

  it("returns a shipped bare array unchanged", async () => {
    const tag = { id: "t1", name: "v1" };
    assert.deepEqual(await readTagList(async () => [tag]), [tag]);
  });

  it("still surfaces non-404 failures", async () => {
    await assert.rejects(
      () =>
        readTagList(async () => {
          throw new Error("500: boom");
        }),
      /500: boom/,
    );
  });
});

describe("readThreadSummaries (listThreads contract)", () => {
  it("lets a thread row from an older backend read .total without crashing", async () => {
    const threads = await readThreadSummaries(async () => [
      {
        id: "6adaf8a3-c0f2-4652-bff4-ae0861a175c7",
        title: "Measuring across a corner",
        claim_count: 0,
      },
    ]);
    assert.equal(threads[0]?.grounding_rollup.total > 0, false);
    assert.deepEqual(threads[0]?.grounding_rollup, EMPTY_GROUNDING_ROLLUP);
  });
});
