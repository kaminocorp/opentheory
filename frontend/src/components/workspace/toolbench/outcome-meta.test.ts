import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { landedStepMeta, resolveOutcomeMeta } from "./outcome.ts";

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

describe("landedStepMeta", () => {
  it("matches ResultView when the step carries proven", () => {
    const fromStep = landedStepMeta({
      instrument: "z3.prove",
      outcome: "result",
      output: { proven: true },
    });
    const fromResultView = resolveOutcomeMeta("z3.prove", "result", { proven: true });
    assert.deepEqual(fromStep, fromResultView);
    assert.equal(fromStep.tone, "ok");
    assert.equal(fromStep.label, "Proven");
  });

  it("does not paint weak-support counterexample search as ok", () => {
    const meta = landedStepMeta({
      instrument: "counterexample.search",
      outcome: "result",
      output: { found: false },
    });
    assert.equal(meta.tone, "warn");
    assert.equal(meta.label, "No witness");
    assert.deepEqual(
      meta,
      resolveOutcomeMeta("counterexample.search", "result", { found: false }),
    );
  });

  it("matches ResultView for a finite table hold", () => {
    const output = { is_relation: true };
    const fromStep = landedStepMeta({
      instrument: "table.derive_column",
      outcome: "result",
      output,
    });
    assert.deepEqual(fromStep, resolveOutcomeMeta("table.derive_column", "result", output));
    assert.equal(fromStep.tone, "warn");
    assert.equal(fromStep.label, "Holds on this table");
  });

  it("does not pass an implicit empty map when output is recorded", () => {
    const withOutput = landedStepMeta({
      instrument: "z3.prove",
      outcome: "result",
      output: { proven: true },
    });
    const emptyLegacy = landedStepMeta({
      instrument: "z3.prove",
      outcome: "result",
    });
    assert.equal(withOutput.tone, "ok");
    assert.equal(emptyLegacy.tone, "warn");
  });
});
