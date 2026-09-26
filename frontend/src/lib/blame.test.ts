import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { blameAuthorLine, blameInstrumentLine, blameMovementLine } from "./blame.ts";
import type { ClaimBlameStep } from "@/types/research";

function step(overrides: Partial<ClaimBlameStep> = {}): ClaimBlameStep {
  return {
    checkpoint_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    created_at: "2026-01-01T00:00:00Z",
    summary: "opened",
    stage: null,
    branch_id: null,
    parent_ids: [],
    author: { id: "actor-1", display_name: "Ada", type: "human" },
    contribution_kind: "create_checkpoint",
    roles: ["asserted"],
    instruments: [],
    agent_run: null,
    signal_after: "none",
    grounding_after: "ungrounded",
    signal_moved: false,
    grounding_moved: false,
    from_signal: null,
    from_grounding: null,
    ...overrides,
  };
}

describe("blameAuthorLine", () => {
  it("joins actor, type, and contribution", () => {
    assert.equal(blameAuthorLine(step()), "Ada · human · create_checkpoint");
  });

  it("degrades when the author is gone", () => {
    assert.equal(
      blameAuthorLine(step({ author: null, contribution_kind: null })),
      "unknown actor · human · checkpoint",
    );
  });
});

describe("blameMovementLine", () => {
  it("is null when nothing moved", () => {
    assert.equal(blameMovementLine(step()), null);
  });

  it("names both axes when both moved", () => {
    assert.equal(
      blameMovementLine(
        step({
          signal_moved: true,
          from_signal: "none",
          signal_after: "validated",
          grounding_moved: true,
          from_grounding: "ungrounded",
          grounding_after: "B",
        }),
      ),
      "signal none → validated · grounding ungrounded → B",
    );
  });
});

describe("blameInstrumentLine", () => {
  it("is null without instruments", () => {
    assert.equal(blameInstrumentLine(step()), null);
  });

  it("lists instrument and status", () => {
    assert.equal(
      blameInstrumentLine(
        step({
          instruments: [
            {
              instrument: "calc.eval",
              status: "result",
              instrument_version: "0.1.0",
              engine: "sympy",
              engine_version: "1.13",
            },
          ],
        }),
      ),
      "calc.eval result",
    );
  });
});
