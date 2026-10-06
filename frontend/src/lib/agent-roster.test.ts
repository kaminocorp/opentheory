import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  ROSTER_UNAVAILABLE_LINE,
  agentSpendLine,
  agentStatusLabel,
  agentStatusTone,
  formatAgentWhen,
  isRosterUnavailable,
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

  it("treats a roster 404 as backend-unavailable, not a raw error", () => {
    assert.equal(isRosterUnavailable(new Error("404: Not Found")), true);
    assert.equal(isRosterUnavailable(new Error("Request failed with 404")), true);
    assert.equal(isRosterUnavailable(new Error("403: Not a member of this project")), false);
    assert.equal(isRosterUnavailable(new Error("500: boom")), false);
    assert.match(ROSTER_UNAVAILABLE_LINE, /isn't available on this backend yet/);
  });
});
