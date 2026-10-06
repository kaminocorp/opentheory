import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  agentSpendLine,
  agentStatusLabel,
  agentStatusTone,
  formatAgentWhen,
  tokenRevealCacheKey,
} from "./agent-roster.ts";

describe("agent roster readout", () => {
  it("marks revoked as fail-weight and active as run", () => {
    assert.equal(agentStatusTone("active"), "run");
    assert.equal(agentStatusTone("suspended"), "warn");
    assert.equal(agentStatusTone("revoked"), "fail");
    assert.equal(agentStatusLabel("revoked"), "revoked");
  });

  it("does not invent billed spend", () => {
    assert.equal(agentSpendLine(0), "no billed spend");
    assert.equal(agentSpendLine(40), "40 tok billed");
  });

  it("says never when last used is missing", () => {
    assert.equal(formatAgentWhen(null), "never");
  });

  it("never turns token plaintext into a cache key", () => {
    assert.equal(tokenRevealCacheKey("eyJhbGciOiJIUzI1NiJ9.payload.sig"), null);
  });
});
