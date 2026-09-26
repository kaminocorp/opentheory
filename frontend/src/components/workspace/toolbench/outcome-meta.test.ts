import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { resolveOutcomeMeta } from "./outcome.ts";

describe("resolveOutcomeMeta", () => {
  it("marks a proof result without proven as warn, never ok", () => {
    const meta = resolveOutcomeMeta("z3.prove", "result", {});
    assert.equal(meta.tone, "warn");
    assert.notEqual(meta.tone, "ok");
  });

  it("marks lean.prove result without proven as warn", () => {
    const meta = resolveOutcomeMeta("lean.prove", "result", {});
    assert.equal(meta.tone, "warn");
  });

  it("emits ok only when proven is true", () => {
    const meta = resolveOutcomeMeta("z3.prove", "result", { proven: true });
    assert.equal(meta.tone, "ok");
    assert.equal(meta.label, "Proven");
  });

  it("treats satisfy result without satisfied as warn", () => {
    const meta = resolveOutcomeMeta("z3.satisfy", "result", {});
    assert.equal(meta.tone, "warn");
  });

  it("downgrades weak-support counterexample search", () => {
    const meta = resolveOutcomeMeta("counterexample.search", "result", { found: false });
    assert.equal(meta.tone, "warn");
    assert.equal(meta.label, "No witness");
  });

  it("keeps a generic calc result as ok", () => {
    const meta = resolveOutcomeMeta("calc.eval", "result", { holds: true });
    assert.equal(meta.tone, "ok");
  });
});
