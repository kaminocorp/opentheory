import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  ROSTER_UNAVAILABLE_LINE,
  agentCapLine,
  agentSpendLine,
  agentStatusLabel,
  agentStatusTone,
  agentTokenCapReached,
  agentUsdCapReached,
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

  it("derives cap-reached from billed vs cap when the 0.58 flag is missing", () => {
    const legacy = {
      token_budget_cap: 50,
      usd_budget_cap: "0.20",
      tokens_used: 50,
      amount: "0.20",
    };
    assert.equal(agentTokenCapReached(legacy), true);
    assert.equal(agentUsdCapReached(legacy), true);
    assert.equal(agentTokenCapReached({ token_budget_cap: 50, tokens_used: 40 }), false);
    assert.equal(agentUsdCapReached({ usd_budget_cap: "0.20", amount: "0.10" }), false);
    assert.equal(agentTokenCapReached({}), false);
    assert.equal(agentUsdCapReached({}), false);
    assert.equal(agentTokenCapReached({ token_cap_reached: true, tokens_used: 0 }), true);
    assert.equal(agentUsdCapReached({ usd_cap_reached: false, usd_budget_cap: "1", amount: "2" }), false);
    assert.equal(agentCapLine({}), "no token cap · no usd cap");
    assert.equal(agentCapLine({ token_budget_cap: 50, usd_budget_cap: "0.20" }), "token cap 50 · usd cap 0.20");
  });

  it("treats a roster 404 as backend-unavailable, not a raw error", () => {
    assert.equal(isRosterUnavailable(new Error("404: Not Found")), true);
    assert.equal(isRosterUnavailable(new Error("Request failed with 404")), true);
    assert.equal(isRosterUnavailable(new Error("403: Not a member of this project")), false);
    assert.equal(isRosterUnavailable(new Error("500: boom")), false);
    assert.match(ROSTER_UNAVAILABLE_LINE, /isn't available on this backend yet/);
  });
});
