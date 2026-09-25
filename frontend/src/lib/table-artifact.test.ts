import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { buildTablePayload, parseCellToken, parseColumnList, parseTableRows } from "./table-artifact.ts";

describe("parseCellToken", () => {
  it("keeps whole numbers as ints", () => {
    assert.equal(parseCellToken("3"), 3);
    assert.equal(parseCellToken("  -12 "), -12);
  });

  it("forwards rationals and labels as strings — no silent float", () => {
    assert.equal(parseCellToken("1/2"), "1/2");
    assert.equal(parseCellToken("0.5"), "0.5");
    assert.equal(parseCellToken("sqrt(2)"), "sqrt(2)");
    assert.equal(parseCellToken("flagship corner"), "flagship corner");
  });
});

describe("parseColumnList / parseTableRows", () => {
  it("splits column names", () => {
    assert.deepEqual(parseColumnList("a, b, d"), ["a", "b", "d"]);
  });

  it("builds rows when the cell count matches", () => {
    assert.deepEqual(parseTableRows(["a", "b", "d"], "3, 4, 5\n5, 12, 13"), [
      { a: 3, b: 4, d: 5 },
      { a: 5, b: 12, d: 13 },
    ]);
  });

  it("rejects a ragged row so Run stays disabled", () => {
    assert.equal(parseTableRows(["a", "b"], "1, 2\n3"), null);
  });
});

describe("buildTablePayload", () => {
  it("omits an empty title", () => {
    assert.deepEqual(buildTablePayload("a", "1", "  "), {
      columns: ["a"],
      rows: [{ a: 1 }],
    });
  });

  it("includes a title when present", () => {
    const payload = buildTablePayload("a, b, d", "3, 4, 5", "integer triples");
    assert.deepEqual(payload, {
      columns: ["a", "b", "d"],
      rows: [{ a: 3, b: 4, d: 5 }],
      title: "integer triples",
    });
  });
});
